# extract_by_id.py
import argparse
import os
import sqlite3
from datetime import datetime, timedelta
import soundfile as sf
import numpy as np
from backend import questdb_client

# --- CONFIGURATION ---
SAMPLE_RATE = 48000  # Ensure this matches your ingested audio's sample rate
OUTPUT_ROOT_DIR = "./event_clips/from_id"
CHUNK_DURATION_SECONDS = 5
# ---------------------

def sanitize_for_path(value: str, fallback='unknown'):
    """Sanitizes a string to be safe for a directory or filename."""
    if not value or not isinstance(value, str) or not value.strip():
        value = fallback
    # Replace spaces with underscores and remove characters invalid for paths
    return value.strip().replace(' ', '_').replace('/', '-').replace('\\', '-')

def fetch_event_details(db_path: str, table_name: str, row_id: int) -> dict | None:
    """
    Connects to an SQLite database and fetches the timestamps, event ID, and
    vehicle type for a specific row ID.
    """
    print(f"Connecting to SQLite DB at '{db_path}' to fetch event details...")
    if not os.path.exists(db_path):
        print(f"ERROR: SQLite database file not found at '{db_path}'")
        return None

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = f"SELECT start_timestamp, end_timestamp, id, vehicle_type FROM {table_name} WHERE rowid = ?"
        print(f"Executing query: {query} with rowid = {row_id}")
        cursor.execute(query, (row_id,))
        
        row = cursor.fetchone()
        conn.close()

        if row:
            print("Successfully fetched event details.")
            return dict(row)
        else:
            print(f"ERROR: No event found in table '{table_name}' with rowid {row_id}.")
            return None
            
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return None

def extract_and_create_flac(db_path: str, table_name: str, row_id: int, step_size: float, padding: float):
    """
    Main function to extract audio based on a SQLite event entry.
    Saves a full-length FLAC and 5-second chunks for each relevant data collection.
    """
    # 1. Get the event details from the SQLite database.
    event_data = fetch_event_details(db_path, table_name, row_id)
    if not event_data:
        return
        
    start_iso_original = event_data['start_timestamp']
    end_iso_original = event_data['end_timestamp']
    event_id_short = event_data['id'][:8]
    vehicle_type = sanitize_for_path(event_data['vehicle_type'])

    # 2. Create a unique parent directory for this extraction run.
    parent_output_dir = os.path.join(OUTPUT_ROOT_DIR, f"event_{event_id_short}_{vehicle_type}")
    os.makedirs(parent_output_dir, exist_ok=True)
    print(f"\nCreated output directory: {parent_output_dir}")

    # 3. Parse and apply padding to timestamps.
    try:
        start_dt_original = datetime.fromisoformat(start_iso_original.replace("Z", "+00:00"))
        end_dt_original = datetime.fromisoformat(end_iso_original.replace("Z", "+00:00"))

        # --- MODIFICATION: Add configurable padding ---
        padding_delta = timedelta(seconds=padding)
        start_dt_padded = start_dt_original - padding_delta
        end_dt_padded = end_dt_original + padding_delta

        start_iso_padded = start_dt_padded.isoformat().replace('+00:00', 'Z')
        end_iso_padded = end_dt_padded.isoformat().replace('+00:00', 'Z')
        
        print(f"Original Time Range: {start_iso_original} -> {end_iso_original}")
        print(f"Padded Time Range (+{padding}s): {start_iso_padded} -> {end_iso_padded}")
        # --- END MODIFICATION ---

    except (ValueError, TypeError):
        print(f"ERROR: Invalid timestamp format in the database for this event.")
        return

    all_collections = questdb_client.get_collections()
    if not all_collections:
        print("ERROR: No collections found in QuestDB.")
        return

    print(f"\nFound {len(all_collections)} collections. Checking each for matching data...")

    # 4. Loop through each collection to find and process overlapping data.
    for collection in all_collections:
        time_range = questdb_client.get_collection_time_range(collection)
        if not time_range:
            continue

        range_start = datetime.fromisoformat(time_range['start'].replace("Z", "+00:00"))
        range_end = datetime.fromisoformat(time_range['end'].replace("Z", "+00:00"))
        
        # Use padded timestamps for checking overlap
        if start_dt_padded <= range_end and end_dt_padded >= range_start:
            print(f"\n  + Match found in '{collection}'. Processing...")
            try:
                # 5. Query the full audio data using the padded duration.
                np_samples = questdb_client.query_raw_audio_data(collection, start_iso_padded, end_iso_padded)

                if np_samples.size == 0:
                    print(f"    - WARNING: No audio data found for '{collection}' in this range.")
                    continue
                
                # 6. Save the full (padded) event FLAC file.
                full_event_filename = f"full_event_{collection}.flac"
                full_event_path = os.path.join(parent_output_dir, full_event_filename)
                sf.write(full_event_path, np_samples, samplerate=SAMPLE_RATE, format='FLAC')
                print(f"    ✓ Saved full event file: {full_event_path}")

                # 7. Create collection-specific sub-folder for chunks.
                collection_output_dir = os.path.join(parent_output_dir, collection)
                os.makedirs(collection_output_dir, exist_ok=True)
                print(f"    - Starting chunking process into: {collection_output_dir}")

                # 8. Perform the chunking.
                chunk_duration_samples = int(CHUNK_DURATION_SECONDS * SAMPLE_RATE)
                step_size_samples = int(step_size * SAMPLE_RATE)
                total_samples = len(np_samples)
                chunks_created = 0

                for i in range(0, total_samples, step_size_samples):
                    chunk_start_sample = i
                    chunk_end_sample = chunk_start_sample + chunk_duration_samples

                    if chunk_end_sample > total_samples:
                        break

                    chunk_samples = np_samples[chunk_start_sample:chunk_end_sample]
                    
                    # Calculate the timestamp for the chunk's filename relative to the padded start time
                    time_offset_seconds = chunk_start_sample / SAMPLE_RATE
                    chunk_start_dt = start_dt_padded + timedelta(seconds=time_offset_seconds)
                    chunk_ts_str = chunk_start_dt.strftime('%Y%m%d_%H%M%S_%f')[:-3]
                    
                    chunk_filename = f"chunk_{chunk_ts_str}.flac"
                    chunk_output_path = os.path.join(collection_output_dir, chunk_filename)
                    
                    sf.write(chunk_output_path, chunk_samples, samplerate=SAMPLE_RATE, format='FLAC')
                    chunks_created += 1
                
                print(f"    ✓ Created {chunks_created} chunks of {CHUNK_DURATION_SECONDS}s with a {step_size}s step.")

            except Exception as e:
                print(f"    ✗ ERROR: Failed during processing for collection '{collection}': {e}")

    print("\n--- Extraction Complete ---")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extracts audio based on a SQLite event entry, saving a full FLAC and chunked FLAC files.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--db", required=True, help="Path to the SQLite database file (e.g., 'test_range.db').")
    parser.add_argument("--table", default='events', help="The name of the table containing the event log (default: 'events').")
    parser.add_argument("--rowid", required=True, type=int, help="The rowid of the specific event entry to extract.")
    parser.add_argument(
        "--step-size",
        type=float,
        default=1.0,
        help="The step size in seconds between the start of each 5-second chunk (default: 1.0)."
    )
    # --- MODIFICATION: Added padding argument ---
    parser.add_argument(
        "--padding",
        type=float,
        default=10.0,
        help="Seconds of padding to add to the beginning AND end of the event's duration (default: 10.0)."
    )
    # --- END MODIFICATION ---

    args = parser.parse_args()
    extract_and_create_flac(args.db, args.table, args.rowid, args.step_size, args.padding)