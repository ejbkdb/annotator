import os
import csv
import json
import sqlite3
from datetime import datetime, timedelta, timezone
import numpy as np
import soundfile as sf
from backend import questdb_client
from multiprocessing import Pool, cpu_count
from tqdm import tqdm


# --- CONFIGURATION ---
INPUT_CSV_FILE = "/home/eborcherding/Documents/annotator/annotated_events_updated.csv"
TIME_OFFSETS_FILE = "/home/eborcherding/Documents/annotator/analysis/time_offsets.json"
OUTPUT_ROOT_DIR = "./event_clips"
CLIP_DATABASE_FILE = "clip_manifest.db"
MIN_DURATION_SECONDS = 5
SAMPLE_RATE = 48000

EXCLUDE_COLLECTIONS = ["my_hardcoded_test", "hellsbay1", "try"]
# ---------------------

# --- PERFORMANCE TUNING ---
NUM_WORKERS = cpu_count()
# --------------------------

# --- GLOBAL CACHE ---
COLLECTION_RANGES_CACHE = {}
# --------------------

def sanitize_for_path(value, fallback='unknown'):
    """Sanitizes a string to be safe for a directory or filename."""
    if not value or not isinstance(value, str) or not value.strip():
        value = fallback
    return value.strip().replace(' ', '_').replace('/', '-').replace('\\', '-')

def init_clip_database():
    """Creates the SQLite database and the 'generated_clips' table if they don't exist."""
    print(f"Initializing clip manifest database at '{CLIP_DATABASE_FILE}'...")
    conn = sqlite3.connect(CLIP_DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS generated_clips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_event_id TEXT NOT NULL,
            vehicle_type TEXT, status TEXT, location TEXT,
            sensor TEXT, action TEXT, direction TEXT,
            start_timestamp_utc TEXT NOT NULL, end_timestamp_utc TEXT NOT NULL,
            duration_seconds REAL, file_path TEXT NOT NULL UNIQUE, file_name TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()

def load_time_offsets():
    """Loads the time offset configuration from the JSON file."""
    try:
        with open(TIME_OFFSETS_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"WARNING: '{TIME_OFFSETS_FILE}' not found. No offsets will be applied.")
        return {}
    return {}

def populate_collection_cache():
    """Fetches all collection time ranges once and stores them in a global cache."""
    print("Fetching and caching time ranges for all available QuestDB collections...")
    all_collections = questdb_client.get_collections()
    
    collections_to_query = [c for c in all_collections if c not in EXCLUDE_COLLECTIONS]
    print(f"Found {len(all_collections)} collections, will search in {len(collections_to_query)} of them.")
    
    for collection in collections_to_query:
        time_range = questdb_client.get_collection_time_range(collection)
        if time_range:
            COLLECTION_RANGES_CACHE[collection] = {
                'start': datetime.fromisoformat(time_range['start'].replace("Z", "+00:00")),
                'end': datetime.fromisoformat(time_range['end'].replace("Z", "+00:00"))
            }

def clip_generation_worker(event_data):
    """
    WORKER FUNCTION: For a single event, finds ALL matching sensors and creates a clip for EACH.
    Returns a LIST of metadata tuples for successful clips.
    """
    event, time_offsets = event_data
    generated_clips_metadata = []

    try:
        # 1. Find ALL matching collections for the event
        event_start_dt = datetime.fromisoformat(event['start_timestamp']).replace(tzinfo=timezone.utc)
        matching_collections = []
        for name, time_range in COLLECTION_RANGES_CACHE.items():
            if time_range['start'] <= event_start_dt <= time_range['end']:
                matching_collections.append(name)
        
        if not matching_collections:
            return [] # Return an empty list if no matches are found

        # --- MODIFICATION START ---
        # Loop through every match instead of treating it as an error
        for collection_name in matching_collections:
            # 2. Apply time offset specific to this collection
            offset_seconds = time_offsets.get(collection_name, 0.0)
            start_dt = datetime.fromisoformat(event['start_timestamp']) + timedelta(seconds=offset_seconds)
            end_dt = datetime.fromisoformat(event['end_timestamp']) + timedelta(seconds=offset_seconds)

            # 3. Ensure minimum duration
            duration = (end_dt - start_dt).total_seconds()
            final_start_dt, final_end_dt = start_dt, end_dt
            if duration < MIN_DURATION_SECONDS:
                center_dt = start_dt + timedelta(seconds=duration / 2)
                half_duration = timedelta(seconds=MIN_DURATION_SECONDS / 2)
                final_start_dt = center_dt - half_duration
                final_end_dt = center_dt + half_duration
            
            # 4. Construct unique output path using the current collection name as the sensor
            status = sanitize_for_path(event.get('status'), 'unknown_status')
            vehicle = sanitize_for_path(event.get('vehicle_type'), 'unknown_vehicle')
            location = sanitize_for_path(event.get('location'), 'unknown_location')
            sensor = sanitize_for_path(collection_name, 'unknown_sensor')
            action = sanitize_for_path(event.get('action'), 'unknown_action')
            direction = sanitize_for_path(event.get('direction'), 'unknown_direction')
            
            output_dir = os.path.join(OUTPUT_ROOT_DIR, vehicle, status, location, sensor, action, direction)
            os.makedirs(output_dir, exist_ok=True)
            
            filename_ts = final_start_dt.strftime('%Y%m%d_%H%M%S')
            filename = f"event_{event['id'][:8]}_{sensor}_{filename_ts}.wav" # Added sensor to filename to guarantee uniqueness
            output_path = os.path.join(output_dir, filename)

            # 5. Query audio and write file
            np_samples = questdb_client.query_raw_audio_data(collection_name, final_start_dt.isoformat(), final_end_dt.isoformat())

            if np_samples.size > 0:
                sf.write(output_path, np_samples, samplerate=SAMPLE_RATE, subtype='PCM_16')
                
                # 6. Add metadata for this specific clip to the list for this worker
                generated_clips_metadata.append((
                    event['id'], event['vehicle_type'], event['status'],
                    event['location'], sensor, event['action'],
                    event['direction'], final_start_dt.isoformat(), final_end_dt.isoformat(),
                    (final_end_dt - final_start_dt).total_seconds(), os.path.abspath(output_path), filename
                ))
        # --- MODIFICATION END ---
        
        return generated_clips_metadata

    except Exception as e:
        print(f"\nERROR processing event {event.get('id', 'N/A')}: {e}")
        return [] # Return empty list on error

def main():
    """Main execution function."""
    init_clip_database()
    time_offsets = load_time_offsets()
    if time_offsets is None: return

    try:
        with open(INPUT_CSV_FILE, 'r') as f:
            events = [row for row in csv.DictReader(f) if row.get('status') in ['refined', 'reviewed']]
    except FileNotFoundError:
        print(f"ERROR: Input file '{INPUT_CSV_FILE}' not found. Run the export script first.")
        return

    if not events:
        print("No 'refined' or 'reviewed' events found in CSV to process.")
        return

    populate_collection_cache()
    tasks = [(event, time_offsets) for event in events]

    print(f"\n--- Starting WAV Clip Generation for {len(tasks)} Events using {NUM_WORKERS} workers ---")
    
    with Pool(processes=NUM_WORKERS) as pool:
        results = list(tqdm(pool.imap_unordered(clip_generation_worker, tasks), total=len(tasks)))

    # Flatten the list of lists returned by the workers
    successful_clips_metadata = [clip_meta for sublist in results for clip_meta in sublist]
    
    if successful_clips_metadata:
        print(f"\nFound {len(successful_clips_metadata)} total clips to generate. Updating manifest database...")
        conn = sqlite3.connect(CLIP_DATABASE_FILE)
        cursor = conn.cursor()
        cursor.executemany("""
            INSERT OR REPLACE INTO generated_clips 
            (source_event_id, vehicle_type, status, location, sensor, action, direction, 
             start_timestamp_utc, end_timestamp_utc, duration_seconds, file_path, file_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, successful_clips_metadata)
        conn.commit()
        conn.close()

    print("\n--- Clipping Complete ---")
    print(f"Successfully generated {len(successful_clips_metadata)} WAV files from {len(events)} events.")
    print(f"Manifest database '{CLIP_DATABASE_FILE}' has been updated.")

if __name__ == "__main__":
    main()