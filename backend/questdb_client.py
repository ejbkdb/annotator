# backend/questdb_client.py
import os
import time
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
from questdb.ingress import Sender, IngressError
import numpy as np
import soundfile as sf
from fastapi import HTTPException
from multiprocessing import Pool, cpu_count

# --- Connection Details ---
QUESTDB_HOST = os.getenv("QUESTDB_HOST", "127.0.0.1")
ILP_PORT = 9009
PG_PORT = 8812
PG_USER = "admin"
PG_PASSWORD = "quest"
PG_DBNAME = "qdb"

# --- Performance Tuning ---
# Use 2-4 parallel processes. More than that leads to diminishing returns due to DB lock contention.
# We leave one core free for the OS and other tasks.
NUM_PROCESSES = max(1, cpu_count() - 1)
# Process ~2M samples per chunk given to a worker process. A good balance of overhead vs. memory.
CHUNK_SIZE = 2_000_000

def _get_pg_connection():
    """Establishes a connection to QuestDB over the PostgreSQL wire protocol."""
    conn_str = f"user={PG_USER} password={PG_PASSWORD} host={QUESTDB_HOST} port={PG_PORT} dbname={PG_DBNAME}"
    return psycopg2.connect(conn_str)

def _ensure_table_exists(table_name: str):
    """Creates and optimally configures a QuestDB table if it doesn't already exist."""
    sanitized_table_name = table_name.replace('-', '_')
    
    # ✅ PARTITION BY HOUR for finer-grained partitions on high-frequency data.
    create_sql = f"""
    CREATE TABLE IF NOT EXISTS "{sanitized_table_name}" (
        amplitude SHORT,
        file SYMBOL,
        ts TIMESTAMP
    ) timestamp(ts) PARTITION BY HOUR;
    """
    
    # ✅ ALTER TABLE to tune for high-throughput writes.
    alter_sql = f"""
    ALTER TABLE "{sanitized_table_name}"
    SET param commitLag = '5s', maxUncommittedRows = 1000000;
    """
    
    try:
        with _get_pg_connection() as conn:
            with conn.cursor() as cur:
                print(f"Ensuring table '{sanitized_table_name}' exists with PARTITION BY HOUR...")
                cur.execute(create_sql)
                
                try:
                    print("Setting optimal commitLag and maxUncommittedRows...")
                    cur.execute(alter_sql)
                except psycopg2.Error as e:
                    # It's okay if this fails on subsequent runs; it means the params are already set.
                    print(f"Note: Could not alter table (likely already configured): {e}")

        return sanitized_table_name
    except Exception as e:
        print(f"Error creating/configuring table '{sanitized_table_name}': {e}")
        raise

def _ingest_worker(args):
    """
    The multiprocessing worker function. It runs in its own process.
    """
    worker_id, chunk_data, table_name, filename = args
    samples, timestamps = chunk_data
    
    print(f"  [Worker {worker_id}] Processing {len(samples):,} points...")
    
    try:
        # Each worker process creates its own Sender.
        with Sender(QUESTDB_HOST, ILP_PORT) as sender:
            for sample, ts in zip(samples.tolist(), timestamps.tolist()):
                sender.row(
                    table_name,
                    symbols={'file': filename},
                    columns={'amplitude': sample},
                    at=ts)
            sender.flush() # Flush at the end of the chunk
        return len(samples)
    except IngressError as e:
        print(f"!! [Worker {worker_id}] Ingress Error: {e}")
        return 0 # Return 0 on failure

def _ingest_orchestrator(filepath: str, collection_name: str):
    """
    Synchronous orchestrator that reads the file and manages the multiprocessing pool.
    This function is designed to be run in a thread pool executor from an async context.
    """
    filename = os.path.basename(filepath)
    sanitized_table_name = _ensure_table_exists(collection_name)
    
    start_timestamp = parse_filename_for_timestamp(filename)
    if not start_timestamp:
        raise ValueError(f"Could not parse timestamp from filename: {filename}")

    print(f"  [Orchestrator] Reading audio file...")
    audio_data, samplerate = sf.read(filepath, dtype='int16', always_2d=False)
    total_points = len(audio_data)
    print(f"  [Orchestrator] Read {total_points:,} samples. Preparing chunks for {NUM_PROCESSES} workers...")

    start_ns = int(start_timestamp.timestamp() * 1_000_000_000)
    ns_per_sample = 1_000_000_000 / samplerate
    timestamps_ns = start_ns + (np.arange(total_points) * ns_per_sample).astype(np.int64)

    # Prepare arguments for each worker
    tasks = []
    for i, start_idx in enumerate(range(0, total_points, CHUNK_SIZE)):
        end_idx = start_idx + CHUNK_SIZE
        chunk_samples = audio_data[start_idx:end_idx]
        chunk_timestamps = timestamps_ns[start_idx:end_idx]
        tasks.append((i + 1, (chunk_samples, chunk_timestamps), sanitized_table_name, filename))

    # Use a multiprocessing Pool to execute workers in parallel
    print(f"  [Orchestrator] Starting Pool with {NUM_PROCESSES} processes to handle {len(tasks)} chunks...")
    start_time = time.time()
    with Pool(processes=NUM_PROCESSES) as pool:
        results = pool.map(_ingest_worker, tasks)
    
    end_time = time.time()
    total_written = sum(results)
    duration = end_time - start_time
    rate = total_written / duration if duration > 0 else 0
    
    print(f"  [Orchestrator] Finished. Wrote {total_written:,} points in {duration:.2f} seconds ({rate:,.0f} points/sec).")
    if total_written != total_points:
        print(f"!! WARNING: Mismatch in points. Expected {total_points:,}, wrote {total_written:,}")


async def ingest_wav_data_async(filepath: str, collection_name: str):
    """
    Async wrapper that runs the synchronous, CPU-bound multiprocessing orchestrator
    in a separate thread pool to avoid blocking the main FastAPI event loop.
    """
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,  # Use the default thread pool executor
        _ingest_orchestrator,
        filepath,
        collection_name
    )

# --- The query functions below are fine, no changes needed from the previous version ---

def parse_filename_for_timestamp(filename: str) -> datetime | None:
    try:
        timestamp_str = os.path.splitext(filename)[0].split('_')[-2] + "_" + os.path.splitext(filename)[0].split('_')[-1]
        return datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
    except (IndexError, ValueError):
        return None

def get_collections() -> list[str]:
    with _get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT name FROM tables();")
            return [row[0] for row in cur.fetchall() if not row[0].startswith('telemetry')]

def query_waveform_data(collection: str, start: str, end: str, points: int) -> list:
    sanitized_table_name = collection.replace('-', '_')
    duration_seconds = (datetime.fromisoformat(end.replace("Z", "")) - datetime.fromisoformat(start.replace("Z", ""))).total_seconds()
    if duration_seconds <= 0: return []
    interval_us = max(1, int(duration_seconds * 1_000_000 / points))
    sql = f"""
    SELECT ts, min(amplitude) as min_val, max(amplitude) as max_val
    FROM "{sanitized_table_name}"
    WHERE ts BETWEEN to_timestamp('{start}') AND to_timestamp('{end}')
    SAMPLE BY {interval_us}u;
    """
    with _get_pg_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql)
            results = cur.fetchall()
            return [{"time": row['ts'].isoformat() + "Z", "min": row['min_val'], "max": row['max_val']} for row in results]

def get_collection_time_range(collection: str) -> dict | None:
    sanitized_table_name = collection.replace('-', '_')
    sql = f'SELECT min(ts), max(ts) FROM "{sanitized_table_name}";'
    with _get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            row = cur.fetchone()
            if row and row[0] and row[1]:
                return {"start": row[0].isoformat() + "Z", "end": row[1].isoformat() + "Z"}
            return None

def query_raw_audio_data(collection: str, start: str, end: str) -> np.ndarray:
    sanitized_table_name = collection.replace('-', '_')
    # ⚠️ Added a hard limit to prevent OOM on very large time ranges.
    sql = f"""
    SELECT amplitude FROM "{sanitized_table_name}"
    WHERE ts BETWEEN to_timestamp('{start}') AND to_timestamp('{end}')
    ORDER BY ts
    LIMIT 20000000;
    """
    with _get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            samples = [row[0] for row in cur.fetchall()]
            return np.array(samples, dtype=np.int16)