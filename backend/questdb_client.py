# backend/questdb_client.py
import os
import asyncio
from datetime import datetime, timezone
from dotenv import load_dotenv
import numpy as np
import librosa
from fastapi import HTTPException

# For querying QuestDB via its PostgreSQL-compatible endpoint
import psycopg2
import psycopg2.extras

# For high-speed ingestion using QuestDB's native ILP implementation
from questdb.ingress import Sender, IngressError

load_dotenv()

# --- Connection Details for QuestDB ---
QDB_HOST = os.getenv("QDB_HOST", "127.0.0.1")
QDB_PORT_PG = int(os.getenv("QDB_PORT_PG", 8812)) # For SQL queries
QDB_PORT_ILP = int(os.getenv("QDB_PORT_ILP", 9009)) # For data ingestion

DB_OPTS = {
    "host": QDB_HOST, "port": QDB_PORT_PG, "user": "admin",
    "password": "quest", "dbname": "qdb"
}

def parse_filename_for_timestamp(filename: str) -> datetime | None:
    try:
        parts = os.path.splitext(filename)[0].split('_')
        timestamp_str = f"{parts[-2]}_{parts[-1]}"
        return datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
    except (IndexError, ValueError):
        return None

# --- Asynchronous Ingestion Function ---
async def ingest_wav_data_async(filepath: str, collection_name: str):
    """
    Reads a WAV file and ingests its samples into QuestDB using the high-speed
    InfluxDB Line Protocol (ILP) client. The questdb-client library handles
    batching and network efficiency automatically.
    """
    filename = os.path.basename(filepath)
    start_timestamp = parse_filename_for_timestamp(filename)
    if not start_timestamp:
        print(f"!!! [QuestDB] FAILED to parse timestamp from {filename}")
        return

    # Load audio data using librosa
    loop = asyncio.get_running_loop()
    audio_data, samplerate = await loop.run_in_executor(
        None, lambda: librosa.load(filepath, sr=None, mono=True, dtype=np.float32)
    )
    audio_data = (audio_data * 32767).astype(np.int16)

    # Prepare timestamps for every sample
    start_ns = int(start_timestamp.timestamp() * 1_000_000_000)
    ns_per_sample = 1_000_000_000 / samplerate
    timestamps_ns = start_ns + (np.arange(len(audio_data)) * ns_per_sample).astype(np.int64)
    
    try:
        # The Sender client handles all buffering and batching for us.
        with Sender(QDB_HOST, QDB_PORT_ILP) as sender:
            for i in range(len(audio_data)):
                sender.row(
                    collection_name,
                    symbols={"source_file": filename},
                    columns={"amplitude": int(audio_data[i])},
                    at_nanosecond=timestamps_ns[i]
                )
            sender.flush()
        print(f"  [QuestDB] SUCCESS: Stored {len(audio_data):,} points for {filename}")
    except IngressError as e:
        print(f"!!! [QuestDB] Ingestion failed: {e}")
        raise e

# --- Synchronous Query Functions ---
def get_collections() -> list[str]:
    """Lists all user-created tables in QuestDB."""
    with psycopg2.connect(**DB_OPTS) as conn, conn.cursor() as cur:
        cur.execute("SHOW TABLES;")
        return [row[0] for row in cur.fetchall() if not row[0].startswith('telemetry')]

def get_collection_time_range(collection: str) -> dict | None:
    """Gets the first and last timestamp for a given table in a single query."""
    sql = f'SELECT min(ts), max(ts) FROM "{collection}";'
    with psycopg2.connect(**DB_OPTS) as conn, conn.cursor() as cur:
        try:
            cur.execute(sql)
            res = cur.fetchone()
            if not res or res[0] is None: return None
            return {
                "start": res[0].isoformat().replace('+00:00', 'Z'),
                "end": res[1].isoformat().replace('+00:00', 'Z')
            }
        except psycopg2.Error: return None

def query_waveform_data(collection: str, start: str, end: str, points: int) -> list:
    """
    Queries aggregated waveform data (min/max) from QuestDB.
    *** FIX: Ensures timestamps are full ISO 8601 UTC format with 'Z'. ***
    """
    start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
    end_dt   = datetime.fromisoformat(end.replace("Z", "+00:00"))
    duration_seconds = (end_dt - start_dt).total_seconds()
    if duration_seconds <= 0: return []

    # Calculate interval in milliseconds, using 'T' for the QuestDB unit.
    interval_ms = max(1, int(duration_seconds * 1000 / points))
    
    sql = f"""
        SELECT ts, min(amplitude), max(amplitude)
        FROM "{collection}"
        WHERE ts BETWEEN '{start}' AND '{end}'
        SAMPLE BY {interval_ms}T
    """


    with psycopg2.connect(**DB_OPTS) as conn, conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()
        
        # --- THIS IS THE CORRECTED DATA MAPPING ---
        data = [
            {
                "time": r[0].isoformat(timespec="milliseconds").replace('+00:00', 'Z'), # <--- Ensures UTC format
                "min": int(r[1]),
                "max": int(r[2]),
            }
            for r in rows
            # Defensively filter any time buckets where min/max might be null
            if r[1] is not None and r[2] is not None
        ]
        return data

def query_raw_audio_data(collection: str, start: str, end: str) -> np.ndarray:
    """
    Fetches raw audio samples. The standard psycopg2 client is efficient,
    so no special "high-performance" vs "fallback" method is needed.
    """
    sql = f'SELECT amplitude FROM "{collection}" WHERE ts BETWEEN \'{start}\' AND \'{end}\' ORDER BY ts'
    with psycopg2.connect(**DB_OPTS) as conn, conn.cursor() as cur:
        try:
            cur.execute(sql)
            return np.array([row[0] for row in cur.fetchall()], dtype=np.int16)
        except psycopg2.Error as e:
            print(f"ERROR: Raw audio query failed: {e}")
            raise HTTPException(status_code=500, detail="Database query for raw audio failed.")