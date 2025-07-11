# backend/influx_client.py
import os
import asyncio
import re
from datetime import datetime, timezone
from dotenv import load_dotenv
import numpy as np
import soundfile as sf

from influxdb_client import InfluxDBClient
from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync
from influxdb_client.client.write_api import WriteOptions
from influxdb_client.client.exceptions import InfluxDBError
from fastapi import HTTPException

load_dotenv()

# --- Connection Details ---
INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://localhost:8086")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN", "my-super-secret-token")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "my-org")

# --- Performance Tuning ---
BATCH_SIZE = 250_000      # Sweet spot for batch size (points)
CHUNK_SIZE = 5_000_000    # In-memory chunk size for processing

def parse_filename_for_timestamp(filename: str) -> datetime | None:
    try:
        timestamp_str = os.path.splitext(filename)[0].split('_')[-2] + "_" + os.path.splitext(filename)[0].split('_')[-1]
        return datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
    except (IndexError, ValueError):
        return None

def line_protocol_generator(samples: np.ndarray, timestamps: np.ndarray, filename: str):
    """
    Memory-efficient generator for creating line protocol strings on the fly.
    """
    measurement = "audio_samples"
    # To keep tag values from getting too long, you could hash the filename
    # For now, we'll use the filename directly.
    tag_set = f"file={filename}"
    
    # ✅ Micro-Optimization: .tolist() is often faster for iteration than looping over a NumPy array.
    for sample, timestamp in zip(samples.tolist(), timestamps.tolist()):
        yield f"{measurement},{tag_set} amplitude={sample}i {timestamp}"


async def ingest_wav_data_async(filepath: str, collection_name: str):
    """
    High-throughput ingestion using a single, optimized writer.
    This is the most robust and scalable approach for storing all raw data.
    """
    filename = os.path.basename(filepath)
    print(f"  [PROD-READY] Processing: {filename}")
    
    start_timestamp = parse_filename_for_timestamp(filename)
    if not start_timestamp:
        raise ValueError(f"Could not parse timestamp from filename: {filename}")

    with InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG) as sync_client:
        if not sync_client.buckets_api().find_bucket_by_name(collection_name):
            sync_client.buckets_api().create_bucket(bucket_name=collection_name, org=INFLUXDB_ORG)

    print(f"  [PROD-READY] Reading audio with soundfile...")
    loop = asyncio.get_running_loop()
    audio_data, samplerate = await loop.run_in_executor(
        None, lambda: sf.read(filepath, dtype='int16', always_2d=False)
    )
    total_points = len(audio_data)
    print(f"  [PROD-READY] Read {total_points:,} samples at {samplerate}Hz.")

    start_ns = int(start_timestamp.timestamp() * 1_000_000_000)
    ns_per_sample = 1_000_000_000 / samplerate
    timestamps_ns = start_ns + (np.arange(total_points) * ns_per_sample).astype(np.int64)
    
    write_options = WriteOptions(
        batch_size=BATCH_SIZE,
        flush_interval=5_000,
        jitter_interval=2_000,
        retry_interval=5_000
    )
    
    print(f"  [PROD-READY] Writing {total_points:,} points with single writer (batch size: {BATCH_SIZE:,})...")
    
    async with InfluxDBClientAsync(
        url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG,
        timeout=600_000, enable_gzip=True, write_options=write_options
    ) as client:
        
        write_api = client.write_api()
        
        for i in range(0, total_points, CHUNK_SIZE):
            end_idx = i + CHUNK_SIZE
            chunk_samples = audio_data[i:end_idx]
            chunk_timestamps = timestamps_ns[i:end_idx]
            
            record_generator = line_protocol_generator(chunk_samples, chunk_timestamps, filename)
            
            await write_api.write(bucket=collection_name, org=INFLUXDB_ORG, record=record_generator)
            
            progress = (min(end_idx, total_points) / total_points) * 100
            print(f"  [PROD-READY] Progress: {progress:.1f}%")
    
    print(f"  [PROD-READY] SUCCESS: Stored all {total_points:,} samples for {filename}")


# --- Patched Query Functions ---

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

        # 🔥 CRITICAL BUG FIX: The min_stream block was missing. It is now correctly defined.
        flux_query = f"""
        min_stream = from(bucket: "{collection}")
          |> range(start: {start}, stop: {end})
          |> filter(fn: (r) => r._measurement == "audio_samples" and r._field == "amplitude")
          |> aggregateWindow(every: {interval_ms}ms, fn: min, createEmpty: false)
          |> set(key: "resample_type", value: "min")
        
        max_stream = from(bucket: "{collection}")
          |> range(start: {start}, stop: {end})
          |> filter(fn: (r) => r._measurement == "audio_samples" and r._field == "amplitude")
          |> aggregateWindow(every: {interval_ms}ms, fn: max, createEmpty: false)
          |> set(key: "resample_type", value: "max")

        union(tables: [min_stream, max_stream])
          |> group(columns: ["_time"])
          |> sort(columns: ["_time"])
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
    # ⚠️ FUNCTIONALITY FIX: The placeholder is replaced with a working query.
    query = f'''
    first = from(bucket: "{collection}")
      |> range(start: 0)
      |> filter(fn: (r) => r._measurement == "audio_samples")
      |> first()
      |> keep(columns: ["_time"])

    last = from(bucket: "{collection}")
      |> range(start: 0)
      |> filter(fn: (r) => r._measurement == "audio_samples")
      |> last()
      |> keep(columns: ["_time"])

    union(tables:[first, last]) |> sort(columns:["_time"])
    '''
    with InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG) as client:
        try:
            results = client.query_api().query(query=query, org=INFLUXDB_ORG)
            times = [record.get_value() for table in results for record in table.records]
            if len(times) < 2: return None
            return {"start": times[0].isoformat().replace('+00:00', 'Z'), "end": times[1].isoformat().replace('+00:00', 'Z')}
        except (IndexError, InfluxDBError):
            return None


def query_raw_audio_data(collection: str, start: str, end: str) -> np.ndarray:
    with InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG, timeout=90_000) as client:
        csv_query = f"""
        from(bucket: "{collection}")
          |> range(start: {start}, stop: {end})
          |> filter(fn: (r) => r["_measurement"] == "audio_samples" and r["_field"] == "amplitude")
          |> sort(columns: ["_time"])
          |> keep(columns: ["_value"])
        """
        try:
            csv_iterator = client.query_api().query_csv(query=csv_query, org=INFLUXDB_ORG)
            samples = [int(row[1]) for row in csv_iterator if row and len(row) > 1 and row[1] != '_value']
            return np.array(samples, dtype=np.int16)
        except Exception as e:
            print(f"ERROR: High-speed CSV query failed: {e}. No fallback for this operation.")
            raise HTTPException(status_code=500, detail=f"Database query for raw audio failed: {e}")