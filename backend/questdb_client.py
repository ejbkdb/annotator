# backend/questdb_client.py
import os
import time
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
# FIX: Import the required TimestampNanos class
from questdb.ingress import Sender, IngressError, TimestampNanos
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
CHUNK_SIZE = 2_000_000

def _sanitize_table_name(name: str) -> str:
    """Consistently sanitizes a collection name into a valid QuestDB table name."""
    return name.replace('-', '_').lower()

def _get_pg_connection():
    """Establishes a connection to QuestDB over the PostgreSQL wire protocol."""
    conn_str = f"user={PG_USER} password={PG_PASSWORD} host={QUESTDB_HOST} port={PG_PORT} dbname={PG_DBNAME}"
    return psycopg2.connect(conn_str)

def _ensure_table_exists(table_name: str):
    """Creates and optimally configures a QuestDB table if it doesn't already exist."""
    sanitized_table_name = _sanitize_table_name(table_name)
    
    create_sql = f"""
    CREATE TABLE IF NOT EXISTS "{sanitized_table_name}" (
        amplitude SHORT,
        file SYMBOL,
        ts TIMESTAMP
    ) timestamp(ts) PARTITION BY HOUR;
    """
    alter_sql = f"""
    ALTER TABLE "{sanitized_table_name}"
    SET param commitLag = '5s', maxUncommittedRows = 5000000;
    """
    try:
        with _get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(create_sql)
                try:
                    cur.execute(alter_sql)
                except psycopg2.Error:
                    pass
        return sanitized_table_name
    except Exception as e:
        print(f"Error creating/configuring table '{sanitized_table_name}': {e}")
        raise

def ingest_worker(task_args):
    """
    The top-level worker function for multiprocessing.
    It runs in its own process and writes one chunk of data to QuestDB.
    """
    worker_id, chunk_data, table_name, filename = task_args
    samples, timestamps = chunk_data
    
    try:
        conf = f"tcp::addr={QUESTDB_HOST}:{ILP_PORT};"
        with Sender.from_conf(conf) as sender:
            for sample, ts in zip(samples, timestamps, strict=True):
                sender.row(
                    table_name,
                    symbols={'file': filename},
                    columns={'amplitude': int(sample)},
                    # FIX: Wrap the integer timestamp in the TimestampNanos struct.
                    at=TimestampNanos(int(ts)))
            sender.flush()
        return len(samples)
    except IngressError as e:
        print(f"!! [Worker {worker_id}] Ingress Error: {e}")
        return 0

def prepare_ingestion_tasks(filepath: str, collection_name: str):
    """
    A synchronous function that reads an audio file and prepares a list of
    task arguments to be consumed by the multiprocessing pool.
    """
    filename = os.path.basename(filepath)
    sanitized_table_name = _ensure_table_exists(collection_name)
    
    start_timestamp = parse_filename_for_timestamp(filename)
    if not start_timestamp:
        raise ValueError(f"Could not parse timestamp from filename: {filename}")

    audio_data, samplerate = sf.read(filepath, dtype='int16', always_2d=False)
    total_points = len(audio_data)

    start_ns = int(start_timestamp.timestamp() * 1_000_000_000)
    ns_per_sample = 1_000_000_000 / samplerate
    timestamps_ns = start_ns + (np.arange(total_points) * ns_per_sample).astype(np.int64)

    tasks = []
    for i, start_idx in enumerate(range(0, total_points, CHUNK_SIZE)):
        end_idx = start_idx + CHUNK_SIZE
        chunk_samples = audio_data[start_idx:end_idx]
        chunk_timestamps = timestamps_ns[start_idx:end_idx]
        tasks.append((i + 1, (chunk_samples, chunk_timestamps), sanitized_table_name, filename))
    
    return tasks

# The query and utility functions below do not require changes.
def parse_filename_for_timestamp(filename: str) -> datetime | None:
    try:
        timestamp_str = os.path.splitext(filename)[0].split('_')[-2] + "_" + os.path.splitext(filename)[0].split('_')[-1]
        return datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
    except (IndexError, ValueError):
        return None

def get_collections() -> list[str]:
    sql = "SELECT table_name FROM tables() WHERE table_name NOT LIKE 'telemetry%'"
    with _get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return [row[0] for row in cur.fetchall()]

def query_waveform_data(collection: str, start: str, end: str, points: int) -> list:
    sanitized_table_name = _sanitize_table_name(collection)
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
    sanitized_table_name = _sanitize_table_name(collection)
    if sanitized_table_name not in get_collections():
        return None
    sql = f'SELECT min(ts), max(ts) FROM "{sanitized_table_name}";'
    with _get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            row = cur.fetchone()
            if row and row[0] and row[1]:
                return {"start": row[0].isoformat() + "Z", "end": row[1].isoformat() + "Z"}
            return None

def query_raw_audio_data(collection: str, start: str, end: str) -> np.ndarray:
    sanitized_table_name = _sanitize_table_name(collection)
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