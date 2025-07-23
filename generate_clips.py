# generate_clips.py
import os
import csv
import json
from datetime import datetime, timedelta, timezone
import numpy as np
import soundfile as sf
from backend import questdb_client

# --- CONFIGURATION ---
INPUT_CSV_FILE = "/home/eborcherding/Documents/annotator/annotated_events_updated.csv"
TIME_OFFSETS_FILE = "analysis/time_offsets.json"
OUTPUT_ROOT_DIR = "./event_clips"
MIN_DURATION_SECONDS = 5
SAMPLE_RATE = 48000
# ---------------------


def sanitize_for_path(value, fallback='unknown'):
    """Sanitizes a string to be safe for a directory or filename."""
    if not value or not isinstance(value, str) or not value.strip():
        value = fallback
    # Replace spaces with underscores and remove characters invalid for paths
    return value.strip().replace(' ', '_').replace('/', '-').replace('\\', '-')

def load_time_offsets():
    """Loads the time offset configuration from the JSON file."""
    try:
        with open(TIME_OFFSETS_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"WARNING: Time offset file '{TIME_OFFSETS_FILE}' not found. No offsets will be applied.")
        return {}
    except json.JSONDecodeError:
        print(f"ERROR: Could not parse '{TIME_OFFSETS_FILE}'. Please check its format.")
        return None

def process_events(time_offsets):
    """Reads the CSV, applies logic, and prepares a list of events to be clipped."""
    try:
        with open(INPUT_CSV_FILE, 'r') as f:
            reader = csv.DictReader(f)
            events = list(reader)
    except FileNotFoundError:
        print(f"ERROR: Input file '{INPUT_CSV_FILE}' not found. Run the export script first.")
        return None

    processed_events = []
    print("Fetching all available QuestDB collections...")
    collections = questdb_client.get_collections()
    print(f"Found {len(collections)} collections: {', '.join(collections)}")

    for i, event in enumerate(events):
        print(f"\n--- Processing Event {i+1}/{len(events)} (ID: {event.get('id', 'N/A')}) ---")

        status = sanitize_for_path(event.get('status'), 'unknown_status')
        if status not in ['refined', 'reviewed']:
            print(f"  INFO: Skipping event with status '{status}'. Only processing 'refined' or 'reviewed' events.")
            continue
        
        # 1. Find the correct collection for the event's timestamp
        event_start_dt = datetime.fromisoformat(event['start_timestamp']).replace(tzinfo=timezone.utc)
        
        collection_name = None
        for collection in collections:
            time_range = questdb_client.get_collection_time_range(collection)
            if time_range:
                range_start = datetime.fromisoformat(time_range['start'].replace("Z", "+00:00"))
                range_end = datetime.fromisoformat(time_range['end'].replace("Z", "+00:00"))
                if range_start <= event_start_dt <= range_end:
                    collection_name = collection
                    break
        
        if not collection_name:
            print(f"  WARNING: Could not find a matching collection for event start time {event['start_timestamp']}. Skipping.")
            continue
        print(f"  Found matching collection: '{collection_name}'")

        # 2. Apply time offset
        offset_seconds = time_offsets.get(collection_name, 0.0)
        start_dt = datetime.fromisoformat(event['start_timestamp']) + timedelta(seconds=offset_seconds)
        end_dt = datetime.fromisoformat(event['end_timestamp']) + timedelta(seconds=offset_seconds)
        if offset_seconds != 0.0:
            print(f"  Applied time offset of {offset_seconds}s.")

        # 3. Ensure minimum duration of 5 seconds
        duration = (end_dt - start_dt).total_seconds()
        if duration < MIN_DURATION_SECONDS:
            center_dt = start_dt + (end_dt - start_dt) / 2
            half_duration = timedelta(seconds=MIN_DURATION_SECONDS / 2)
            start_dt = center_dt - half_duration
            end_dt = center_dt + half_duration
            print(f"  Event duration was {duration:.2f}s. Padded to {MIN_DURATION_SECONDS}s.")

        # 4. Construct output path and filename based on the new structure
        # --- MODIFICATION START ---
        # New folder structure: vehicle > status > location > sensor > action > direction
        vehicle = sanitize_for_path(event.get('vehicle_type'), 'unknown_vehicle')
        location = sanitize_for_path(event.get('location'), 'unknown_location')
        sensor = sanitize_for_path(collection_name, 'unknown_sensor')
        action = sanitize_for_path(event.get('action'), 'unknown_action')
        direction = sanitize_for_path(event.get('direction'), 'unknown_direction')
        
        output_dir = os.path.join(OUTPUT_ROOT_DIR, vehicle, status, location, sensor, action, direction)
        # --- MODIFICATION END ---
        
        filename_ts = start_dt.strftime('%Y%m%d_%H%M%S')
        filename = f"event_{event['id'][:8]}_{filename_ts}.wav"
        output_path = os.path.join(output_dir, filename)

        processed_events.append({
            "collection": collection_name,
            "start_iso": start_dt.isoformat(),
            "end_iso": end_dt.isoformat(),
            "output_path": output_path,
            "id": event['id']
        })
        print(f"  Prepared for clipping. Output: {output_path}")

    return processed_events

def create_wav_clips(events_to_clip):
    """Queries QuestDB and writes the WAV file clips."""
    if not events_to_clip:
        print("No events to process for clipping.")
        return

    print(f"\n--- Starting WAV Clip Generation for {len(events_to_clip)} Events ---")
    
    success_count = 0
    for i, event_data in enumerate(events_to_clip):
        print(f"  [{i+1}/{len(events_to_clip)}] Clipping event ID {event_data['id'][:8]}...")
        try:
            # 1. Ensure output directory exists
            output_dir = os.path.dirname(event_data['output_path'])
            os.makedirs(output_dir, exist_ok=True)

            # 2. Query raw audio data
            np_samples = questdb_client.query_raw_audio_data(
                event_data['collection'],
                event_data['start_iso'],
                event_data['end_iso']
            )

            if np_samples.size == 0:
                print(f"    WARNING: No audio data found for the requested range. Skipping.")
                continue

            # 3. Write to WAV file
            sf.write(event_data['output_path'], np_samples, samplerate=SAMPLE_RATE, subtype='PCM_16')
            print(f"    ✓ Successfully saved: {event_data['output_path']}")
            success_count += 1

        except Exception as e:
            print(f"    ✗ ERROR: Failed to create clip for event {event_data['id']}: {e}")
            
    print("\n--- Clipping Complete ---")
    print(f"Successfully generated {success_count}/{len(events_to_clip)} WAV files.")

if __name__ == "__main__":
    offsets = load_time_offsets()
    if offsets is not None:
        prepared_data = process_events(offsets)
        if prepared_data:
            create_wav_clips(prepared_data)