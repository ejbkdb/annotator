# backend/questdb_client.py
import os
import time
from datetime import datetime, timezone
import psycopg2
from psycopg2.extras import RealDictCursor
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
CHUNK_SIZE = 2_000_000  # Number of samples to process in each chunk

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
    """
    Ensures a datetime object is timezone-aware (as UTC) and formats it
    as a standard ISO 8601 string with a 'Z' suffix.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")

# --- CRITICAL FIX: Ensure parsed timestamps are timezone-aware ---
def parse_filename_for_timestamp(filename: str) -> datetime | None:
    """Parses a filename like '..._YYYYMMDD_HHMMSS.WAV' into a UTC datetime object."""
    try:
        parts = os.path.splitext(filename)[0].split('_')
        timestamp_str = f"{parts[-2]}_{parts[-1]}"
        # Create a naive datetime and then make it explicitly UTC
        naive_dt = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
        return naive_dt.replace(tzinfo=timezone.utc)
    except (IndexError, ValueError):
        return None

# --- Ingestion Pipeline ---

def ingest_worker(task_args):
    """The top-level worker function for multiprocessing."""
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
                    at=TimestampNanos(int(ts)))
            sender.flush()
        return len(samples)
    except IngressError as e:
        print(f"!! [Worker {worker_id}] Ingress Error: {e}")
        return 0

def prepare_ingestion_tasks(filepath: str, collection_name: str):
    """Reads an audio file and prepares a list of tasks for the multiprocessing pool."""
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

# --- Data Query Functions ---

def get_collections() -> list[str]:
    """Lists all user-created tables in QuestDB."""
    sql = "SELECT table_name FROM tables() WHERE table_name NOT LIKE 'telemetry%'"
    with _get_pg_connection() as conn, conn.cursor() as cur:
        cur.execute(sql)
        return [row[0] for row in cur.fetchall()]

def get_collection_time_range(collection: str) -> dict | None:
    """Gets the first and last timestamp for a given table, formatted as UTC ISO strings."""
    sql = f'SELECT min(ts), max(ts) FROM "{_sanitize_table_name(collection)}";'
    try:
        with _get_pg_connection() as conn, conn.cursor() as cur:
            cur.execute(sql)
            res = cur.fetchone()
            if not res or res[0] is None: 
                return None
            # Use the helper to ensure clean 'Z' formatted UTC strings are returned
            return {"start": _to_utc_iso(res[0]), "end": _to_utc_iso(res[1])}
    except psycopg2.Error as e:
        print(f"Database query for time range failed: {e}")
        return None

def query_waveform_data(collection: str, start: str, end: str, points: int) -> list:
    """Queries aggregated waveform data (min/max) from QuestDB."""
    start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
    end_dt   = datetime.fromisoformat(end.replace("Z", "+00:00"))
    duration_seconds = (end_dt - start_dt).total_seconds()
    if duration_seconds <= 0: 
        return []

    interval_ms = max(1, int(duration_seconds * 1000 / points))
    
    sql = f"""
        SELECT ts, min(amplitude), max(amplitude)
        FROM "{_sanitize_table_name(collection)}"
        WHERE ts BETWEEN '{start}' AND '{end}'
        SAMPLE BY {interval_ms}T
    """
    with _get_pg_connection() as conn, conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()
        # Use the helper to ensure clean 'Z' formatted UTC strings are returned
        data = [
            {
                "time": _to_utc_iso(r[0]),
                "min": int(r[1]),
                "max": int(r[2]),
            }
            for r in rows
            if r[1] is not None and r[2] is not None
        ]
        return data

def query_raw_audio_data(collection: str, start: str, end: str) -> np.ndarray:
    """Fetches raw audio samples for playback."""
    
    # --- START OF THE FIX ---
    # The SQL query is modified to remove the to_timestamp() calls.
    # We will let QuestDB perform its own string-to-timestamp casting,
    # which is proven to work correctly with the Z-suffixed ISO strings.
    sql = f"""
    SELECT amplitude FROM "{_sanitize_table_name(collection)}"
    WHERE ts BETWEEN '{start}' AND '{end}'
    ORDER BY ts
    LIMIT 20000000;
    """
    # --- END OF THE FIX ---
    
    with _get_pg_connection() as conn, conn.cursor() as cur:
        try:
            cur.execute(sql)
            return np.array([row[0] for row in cur.fetchall()], dtype=np.int16)
        except psycopg2.Error as e:
            print(f"ERROR: Raw audio query failed: {e}")
            raise HTTPException(status_code=500, detail="Database query for raw audio failed.")