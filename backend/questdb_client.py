# backend/questdb_client.py
import os
import time
from datetime import datetime, timezone
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import errors as pg_errors
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

# --- Helper Functions ---

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
    try:
        with _get_pg_connection() as conn, conn.cursor() as cur:
            cur.execute(create_sql)
        return sanitized_table_name
    except Exception as e:
        print(f"Error creating/configuring table '{sanitized_table_name}': {e}")
        raise

def _to_utc_iso(dt: datetime) -> str:
    """Ensures a datetime object is timezone-aware and formats it to the standard ISO 8601 UTC format."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")

def parse_filename_for_timestamp(filename: str) -> datetime | None:
    """Parses a filename into a timezone-aware UTC datetime object."""
    try:
        parts = os.path.splitext(filename)[0].split('_')
        timestamp_str = f"{parts[-2]}_{parts[-1]}"
        naive_dt = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
        return naive_dt.replace(tzinfo=timezone.utc)
    except (IndexError, ValueError):
        return None

# --- Ingestion Pipeline ---
# (No changes needed here, this part is correct)
def ingest_worker(task_args):
    worker_id, chunk_data, table_name, filename = task_args
    samples, timestamps = chunk_data
    try:
        conf = f"tcp::addr={QUESTDB_HOST}:{ILP_PORT};"
        with Sender.from_conf(conf) as sender:
            for sample, ts in zip(samples, timestamps, strict=True):
                sender.row(table_name, symbols={'file': filename}, columns={'amplitude': int(sample)}, at=TimestampNanos(int(ts)))
            sender.flush()
        return len(samples)
    except IngressError as e:
        print(f"!! [Worker {worker_id}] Ingress Error: {e}")
        return 0

def prepare_ingestion_tasks(filepath: str, collection_name: str):
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
# --- End of Ingestion Pipeline ---


# --- Data Query Functions ---

def get_collections() -> list[str]:
    sql = "SELECT table_name FROM tables() WHERE table_name NOT LIKE 'telemetry%'"
    with _get_pg_connection() as conn, conn.cursor() as cur:
        cur.execute(sql)
        return [row[0] for row in cur.fetchall()]

def get_collection_time_range(collection: str) -> dict | None:
    sanitized_collection = _sanitize_table_name(collection)
    sql = f'SELECT min(ts), max(ts) FROM "{sanitized_collection}";'
    try:
        with _get_pg_connection() as conn, conn.cursor() as cur:
            cur.execute(sql)
            res = cur.fetchone()
            if not res or res[0] is None:
                return None
            return {"start": _to_utc_iso(res[0]), "end": _to_utc_iso(res[1])}
    except pg_errors.UndefinedTable:
        return None
    except psycopg2.Error as e:
        print(f"Database query for time range failed: {e}")
        return None

def query_waveform_data(collection: str, start: str, end: str, points: int) -> list:
    """Queries aggregated waveform data (min/max) from QuestDB."""
    sanitized_collection = _sanitize_table_name(collection) # Sanitize first
    start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
    duration_seconds = (end_dt - start_dt).total_seconds()
    if duration_seconds <= 0:
        return []

    interval_ms = max(1, int(duration_seconds * 1000 // points))

    # --- THE ACTUAL FIX ---
    # Reverted from 'ms' to 'T' for compatibility with QuestDB 8.0.3.
    # Kept the robust sanitization and exception handling.
    sql = f"""
        SELECT ts, min(amplitude), max(amplitude)
        FROM "{sanitized_collection}"
        WHERE ts BETWEEN '{start}' AND '{end}'
        SAMPLE BY {interval_ms}T
    """
    
    with _get_pg_connection() as conn, conn.cursor() as cur:
        try:
            cur.execute(sql)
            rows = cur.fetchall()
            return [
                {"time": _to_utc_iso(r[0]), "min": int(r[1]), "max": int(r[2])}
                for r in rows if r[1] is not None and r[2] is not None
            ]
        except pg_errors.UndefinedTable:
            raise HTTPException(status_code=404, detail=f"Collection '{collection}' not found.")
        except pg_errors.DatabaseError as e:
            print(f"ERROR: Waveform query failed for collection '{collection}': {e}")
            raise HTTPException(status_code=500, detail=f"QuestDB query failed: {e}")

def query_raw_audio_data(collection: str, start: str, end: str) -> np.ndarray:
    """Fetches raw audio samples for playback."""
    sanitized_collection = _sanitize_table_name(collection) # Sanitize first
    
    sql = f"""
    SELECT amplitude FROM "{sanitized_collection}"
    WHERE ts BETWEEN '{start}' AND '{end}'
    ORDER BY ts
    LIMIT 20000000;
    """
    
    with _get_pg_connection() as conn, conn.cursor() as cur:
        try:
            cur.execute(sql)
            results = cur.fetchall()
            if not results:
                return np.array([], dtype=np.int16)
            return np.array([row[0] for row in results], dtype=np.int16)
        except pg_errors.UndefinedTable:
            raise HTTPException(status_code=404, detail=f"Collection '{collection}' not found.")
        except pg_errors.DatabaseError as e:
            print(f"ERROR: Raw audio query failed for '{collection}': {e}")
            raise HTTPException(status_code=500, detail=f"QuestDB query for raw audio failed: {e}")

def check_data_exists(collection: str, start: str, end: str) -> bool:
    """Efficiently checks if any data points exist in a given collection within a specific time range."""
    sanitized_table_name = _sanitize_table_name(collection)
    sql = f"SELECT 1 FROM \"{sanitized_table_name}\" WHERE ts BETWEEN '{start}' AND '{end}' LIMIT 1;"

    try:
        with _get_pg_connection() as conn, conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchone() is not None
    except pg_errors.UndefinedTable:
        return False
    except psycopg2.Error:
        return False