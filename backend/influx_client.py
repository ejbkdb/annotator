# backend/influx_client.py
import os
import asyncio
from datetime import datetime, timezone
from dotenv import load_dotenv

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync
from influxdb_client.client.exceptions import InfluxDBError
from fastapi import HTTPException # Import HTTPException for re-raising errors
import librosa
import numpy as np

load_dotenv()

# --- Connection Details ---
INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://localhost:8086")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN", "my-super-secret-token")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "my-org")

# --- OPTIMIZATION SETTINGS ---
BATCH_SIZE = 100000  # Points per batch for efficient writes

def parse_filename_for_timestamp(filename: str) -> datetime | None:
    try:
        timestamp_str = os.path.splitext(filename)[0].split('_')[-2] + "_" + os.path.splitext(filename)[0].split('_')[-1]
        return datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
    except (IndexError, ValueError):
        return None

# --- Asynchronous Ingestion Function ---
async def ingest_wav_data_async(filepath: str, collection_name: str):
    """Fast asynchronous WAV ingestion using librosa and optimized batching."""
    
    filename = os.path.basename(filepath)
    print(f"  [fast] Processing: {filename}")
    
    start_timestamp = parse_filename_for_timestamp(filename)
    if not start_timestamp:
        print(f"!!! [fast] FAILED to parse timestamp from {filename}")
        return

    print(f"  [fast] Checking if bucket '{collection_name}' exists...")
    
    sync_client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
    try:
        buckets_api = sync_client.buckets_api()
        bucket = buckets_api.find_bucket_by_name(collection_name)
        if not bucket:
            print(f"  [fast] Bucket '{collection_name}' not found. Creating...")
            buckets_api.create_bucket(bucket_name=collection_name, org=INFLUXDB_ORG)
            print(f"  [fast] Bucket '{collection_name}' created successfully.")
        else:
            print(f"  [fast] Bucket '{collection_name}' already exists.")
    finally:
        sync_client.close()

    print(f"  [fast] Reading audio with librosa...")
    loop = asyncio.get_running_loop()
    
    audio_data, samplerate = await loop.run_in_executor(
        None, 
        lambda: librosa.load(filepath, sr=None, mono=True, dtype=np.float32)
    )
    
    audio_data = (audio_data * 32767).astype(np.int16)
    
    print(f"  [fast] Read {len(audio_data):,} samples at {samplerate}Hz ({len(audio_data)/samplerate:.1f} seconds)")

    start_ns = int(start_timestamp.timestamp() * 1_000_000_000)
    ns_per_sample = 1_000_000_000 / samplerate
    sample_indices = np.arange(len(audio_data))
    timestamps_ns = start_ns + (sample_indices * ns_per_sample).astype(np.int64)
    
    async with InfluxDBClientAsync(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG, timeout=300_000) as client:
        write_api = client.write_api()
        
        total_points = len(audio_data)
        batches_written = 0
        
        print(f"  [fast] Writing {total_points:,} points in batches of {BATCH_SIZE:,}...")
        
        for i in range(0, total_points, BATCH_SIZE):
            end_idx = min(i + BATCH_SIZE, total_points)
            batch_data = audio_data[i:end_idx]
            batch_timestamps = timestamps_ns[i:end_idx]
            
            lines = [
                f"audio_samples,source_file={filename} amplitude={int(sample)}i {timestamp}"
                for sample, timestamp in zip(batch_data, batch_timestamps)
            ]
            
            try:
                await write_api.write(bucket=collection_name, org=INFLUXDB_ORG, record=lines)
                batches_written += 1
                
                if batches_written % 5 == 0:
                    progress = (end_idx / total_points) * 100
                    print(f"  [fast] Progress: {progress:.1f}% ({end_idx:,}/{total_points:,} points)")
                
                await asyncio.sleep(0.005)
                
            except InfluxDBError as e:
                print(f"!!! [fast] Batch write failed: {e}")
                raise e
    
    duration_minutes = len(audio_data) / samplerate / 60
    print(f"  [fast] SUCCESS: Stored {total_points:,} points ({duration_minutes:.1f} minutes of audio) in {batches_written} batches for {filename}")

# --- Synchronous Query Functions ---
def get_collections() -> list[str]:
    with InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG) as client:
        buckets_api = client.buckets_api()
        buckets = buckets_api.find_buckets(org=INFLUXDB_ORG).buckets
        return [b.name for b in buckets if not b.name.startswith('_')]

def query_waveform_data(collection: str, start: str, end: str, points: int) -> list:
    with InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG, timeout=90_000) as client:
        query_api = client.query_api()
        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
        duration_seconds = (end_dt - start_dt).total_seconds()
        
        if duration_seconds <= 0: return []
        
        interval_ms = max(1, int(duration_seconds * 1000 / points))

        flux_query = f"""
        min_stream = from(bucket: "{collection}") |> range(start: {start}, stop: {end}) |> filter(fn: (r) => r._measurement == "audio_samples" and r._field == "amplitude") |> aggregateWindow(every: {interval_ms}ms, fn: min, createEmpty: false) |> set(key: "resample_type", value: "min")
        max_stream = from(bucket: "{collection}") |> range(start: {start}, stop: {end}) |> filter(fn: (r) => r._measurement == "audio_samples" and r._field == "amplitude") |> aggregateWindow(every: {interval_ms}ms, fn: max, createEmpty: false) |> set(key: "resample_type", value: "max")
        union(tables: [min_stream, max_stream]) |> group(columns: ["_time"]) |> sort(columns: ["_time"])
        """
        try:
            results = query_api.query(query=flux_query, org=INFLUXDB_ORG)
            data_map = {}
            for table in results:
                for record in table.records:
                    time_key = record.get_time().isoformat()
                    if time_key not in data_map: data_map[time_key] = {}
                    data_map[time_key][record.values['resample_type']] = record.get_value()
            data = [{"time": time, "min": values.get("min"), "max": values.get("max")} for time, values in data_map.items() if "min" in values and "max" in values]
            data.sort(key=lambda x: x['time'])
            return data
        except InfluxDBError as e:
            print(f"InfluxDB query failed: {e}")
            raise e

def get_collection_time_range(collection: str) -> dict | None:
    start_query = f'from(bucket: "{collection}") |> range(start: 0) |> first()'
    end_query = f'from(bucket: "{collection}") |> range(start: 0) |> last()'
    with InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG) as client:
        query_api = client.query_api()
        try:
            start_tables = query_api.query(query=start_query, org=INFLUXDB_ORG)
            start_time = start_tables[0].records[0].get_time() if start_tables and start_tables[0].records else None
            end_tables = query_api.query(query=end_query, org=INFLUXDB_ORG)
            end_time = end_tables[0].records[0].get_time() if end_tables and end_tables[0].records else None
            if not start_time or not end_time: return None
            return {"start": start_time.isoformat().replace('+00:00', 'Z'), "end": end_time.isoformat().replace('+00:00', 'Z')}
        except (IndexError, InfluxDBError):
            return None

def query_raw_audio_data(collection: str, start: str, end: str) -> np.ndarray:
    """
    Fetches raw amplitude values using a high-performance CSV query with a reliable fallback.
    """
    with InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG, timeout=90_000) as client:
        query_api = client.query_api()

        # --- ATTEMPT 1: High-performance CSV query ---
        try:
            csv_query = f"""
            from(bucket: "{collection}")
              |> range(start: {start}, stop: {end})
              |> filter(fn: (r) => r["_measurement"] == "audio_samples" and r["_field"] == "amplitude")
              |> sort(columns: ["_time"])
              |> keep(columns: ["_value"])
            """
            print(f"Attempting high-speed CSV query for raw audio between {start} and {end}...")
            csv_iterator = query_api.query_csv(query=csv_query, org=INFLUXDB_ORG)
            
            samples = []
            is_header = True
            value_index = -1

            for csv_row in csv_iterator:
                if is_header:
                    try:
                        value_index = csv_row.index('_value')
                        is_header = False
                        print(f"DEBUG: CSV header found: {csv_row}. '_value' is at index {value_index}.")
                    except ValueError:
                        print(f"DEBUG: Skipping non-header CSV row: {csv_row}")
                        continue
                    continue

                if value_index != -1 and len(csv_row) > value_index:
                    try:
                        samples.append(int(csv_row[value_index]))
                    except (ValueError, TypeError):
                        continue
            
            if samples:
                print(f"SUCCESS: Extracted {len(samples)} samples via high-speed CSV method.")
                return np.array(samples, dtype=np.int16)
            
            print("WARNING: CSV query executed but returned 0 samples. Will try fallback method.")

        except Exception as e:
            print(f"ERROR: High-speed CSV query failed with exception: {e}. Falling back to standard method.")

        # --- ATTEMPT 2: Standard, reliable query (Fallback) ---
        print("Attempting standard fallback query...")
        standard_query = f"""
        from(bucket: "{collection}")
          |> range(start: {start}, stop: {end})
          |> filter(fn: (r) => r["_measurement"] == "audio_samples" and r["_field"] == "amplitude")
          |> sort(columns: ["_time"])
        """
        try:
            results = query_api.query(query=standard_query, org=INFLUXDB_ORG)
            samples = [record.get_value() for table in results for record in table.records]
            print(f"SUCCESS: Extracted {len(samples)} samples via standard fallback method.")
            return np.array(samples, dtype=np.int16)
        
        except InfluxDBError as e:
            print(f"ERROR: Standard fallback query also failed: {e}")
            raise HTTPException(status_code=500, detail=f"Database query failed on both CSV and standard methods: {e}")