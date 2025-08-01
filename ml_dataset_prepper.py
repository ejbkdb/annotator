# ml_dataset_prepper.py
import sqlite3
import os
import argparse
from datetime import datetime, timedelta
from collections import defaultdict
import numpy as np
import pandas as pd
import soundfile as sf
from tqdm import tqdm
import matplotlib.pyplot as plt
import seaborn as sns

# This import assumes you run the script from the project's root directory
from backend import questdb_client

# --- CONFIGURATION ---
DATABASE_FILE = "/home/eborcherding/Documents/annotator/test_range.db"
CORRECTED_TABLE_NAME = "corrected_annotations"
MANIFEST_TABLE_NAME = "flac_manifest"
ANALYSIS_OUTPUT_DIR = "analysis_plots"
FLAC_OUTPUT_DIR = "flac_dataset"
SAMPLE_RATE = 48000
CLIP_DURATION_S = 5.0

# --- ADVANCED WINDOWING & OVERLAP STRATEGY ---
ADVANCED_WINDOWING_CONFIG = {
    "vehicle_specific": {
        "mini helicopter": {
            "flying": {'overlap_s': 2.5}
        }
    },
    "general": {
        'driveby': {'overlap_s': 3.0},
        'rev':     {'overlap_s': 3.0},
        'flying':  {'gap_s': 1.5},
        'idle':    {'overlap_s': 2.0},
    },
    "default": {'overlap_s': 2.0}
}


# --- SPECIAL HANDLING FOR MID-LENGTH EVENTS ---
SPECIAL_HANDLING_CONFIG = {
    'max_duration_s': 8.0,
    'num_clips': 3
}
# ---------------------------------------------


def init_manifest_db():
    """
    Initializes the manifest database. It drops the existing manifest table
    to ensure a clean slate for each generation run, preventing stale entries.
    """
    print(f"Initializing manifest table '{MANIFEST_TABLE_NAME}' in '{DATABASE_FILE}'...")
    with sqlite3.connect(DATABASE_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute(f"DROP TABLE IF EXISTS {MANIFEST_TABLE_NAME}")
        cursor.execute(f"""
            CREATE TABLE {MANIFEST_TABLE_NAME} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_annotation_id TEXT NOT NULL,
                vehicle_type TEXT,
                action TEXT,
                location TEXT,
                sensor TEXT,
                clip_start_utc TEXT NOT NULL,
                clip_end_utc TEXT NOT NULL,
                duration_seconds REAL,
                file_path TEXT NOT NULL UNIQUE,
                file_name TEXT NOT NULL
            );
        """)
    print("Manifest table initialized successfully.")


def get_windowing_config(vehicle_type, action):
    # ... (code is unchanged) ...
    vehicle_rules = ADVANCED_WINDOWING_CONFIG["vehicle_specific"].get(vehicle_type, {})
    if action in vehicle_rules:
        return vehicle_rules[action]
    if action in ADVANCED_WINDOWING_CONFIG["general"]:
        return ADVANCED_WINDOWING_CONFIG["general"][action]
    return ADVANCED_WINDOWING_CONFIG["default"]


def generate_clip_windows(start_dt, end_dt, vehicle_type, action):
    # ... (code is unchanged) ...
    windows = []
    event_duration_s = (end_dt - start_dt).total_seconds()

    if event_duration_s < CLIP_DURATION_S:
        return []

    if event_duration_s <= SPECIAL_HANDLING_CONFIG['max_duration_s']:
        windows.append((start_dt, start_dt + timedelta(seconds=CLIP_DURATION_S)))
        windows.append((end_dt - timedelta(seconds=CLIP_DURATION_S), end_dt))
        center_dt = start_dt + timedelta(seconds=event_duration_s / 2)
        half_clip = timedelta(seconds=CLIP_DURATION_S / 2)
        windows.append((center_dt - half_clip, center_dt + half_clip))
        return list(set(windows))

    config = get_windowing_config(vehicle_type, action)
    
    if 'overlap_s' in config:
        step_s = CLIP_DURATION_S - config['overlap_s']
    elif 'gap_s' in config:
        step_s = CLIP_DURATION_S + config['gap_s']
    else:
        step_s = CLIP_DURATION_S - 2.0

    current_start_dt = start_dt
    while current_start_dt + timedelta(seconds=CLIP_DURATION_S) <= end_dt:
        windows.append((current_start_dt, current_start_dt + timedelta(seconds=CLIP_DURATION_S)))
        current_start_dt += timedelta(seconds=step_s)
        
    return windows


def get_all_potential_clips():
    # ... (code is unchanged) ...
    print(f"Connecting to database and querying table '{CORRECTED_TABLE_NAME}'...")
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {CORRECTED_TABLE_NAME}")
        all_events = cursor.fetchall()
        conn.close()
    except sqlite3.OperationalError:
        print(f"\nFATAL ERROR: The table '{CORRECTED_TABLE_NAME}' does not exist.")
        print("Please run 'apply_time_offsets.py' first to generate the corrected lookup data.")
        return None

    if not all_events:
        print("No events found in the lookup table.")
        return []

    print(f"Found {len(all_events)} event lookup rows. Verifying data existence in QuestDB and calculating final clips...")
    
    verified_clips = []
    for event in tqdm(all_events, desc="Validating Events in QuestDB"):
        start_dt = datetime.fromisoformat(event['corrected_start_utc'])
        end_dt = datetime.fromisoformat(event['corrected_end_utc'])
        
        clip_windows = generate_clip_windows(start_dt, end_dt, event['vehicle_type'], event['action'])
        
        for i, (clip_start, clip_end) in enumerate(clip_windows):
            data_exists = questdb_client.check_data_exists(
                collection=event['target_sensor'],
                start=clip_start.isoformat(),
                end=clip_end.isoformat()
            )
            
            if data_exists:
                verified_clips.append({
                    **event,
                    "clip_start_utc": clip_start,
                    "clip_end_utc": clip_end,
                    "clip_index": i
                })
            
    return verified_clips


def run_analysis(clips):
    # ... (code is unchanged, see previous versions) ...
    if not clips:
        print("No verifiable clips were found with the current configuration. Cannot run analysis.")
        return

    print(f"\n--- DATASET BALANCE ANALYSIS ---")
    print(f"Total VERIFIED 5-second clips with current settings: {len(clips)}")
    os.makedirs(ANALYSIS_OUTPUT_DIR, exist_ok=True)

    df = pd.DataFrame(clips)
    sns.set_theme(style="whitegrid")

    breakdowns = {
        "Vehicle Type": ("vehicle_type", None),
        "Action Type": ("action", None),
        "Vehicle Type by Location": (["location", "vehicle_type"], "stack"),
        "Action Type by Location": (["location", "action"], "stack"),
    }

    for title, (group_keys, plot_style) in breakdowns.items():
        print("\n" + "="*50)
        print(f"📊 Breakdown by: {title}")
        print("="*50)
        
        counts = df.groupby(group_keys).size()
        if plot_style == "stack":
            counts = counts.unstack(fill_value=0)
        
        print(counts.to_string())
        
        plt.figure(figsize=(14, 8))
        plot_title = f"Clip Count by {title}"
        if plot_style == "stack":
            counts.plot(kind='bar', stacked=True, ax=plt.gca(), colormap='viridis')
        else:
            sns.barplot(x=counts.index, y=counts.values, palette='viridis')

        plt.title(plot_title, fontsize=16)
        plt.ylabel("Number of 5-Second Clips")
        plt.xlabel(title.split(' by ')[0])
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        
        filename = os.path.join(ANALYSIS_OUTPUT_DIR, f"balance_{title.replace(' ', '_').lower()}.png")
        plt.savefig(filename)
        plt.close()
        print(f"\nSaved plot to: {filename}")

    print("\nAnalysis complete. The generated report accurately reflects the data available in QuestDB.")


def run_generation(clips):
    """
    Generates the .flac files with a new hierarchy and creates a manifest
    table in the SQLite database with metadata for each file.
    """
    if not clips:
        print("No verifiable clips were found with the current configuration. Nothing to generate.")
        return
        
    print(f"\n--- FLAC FILE GENERATION ---")
    print(f"Preparing to generate {len(clips)} VERIFIED audio files...")
    
    response = input(f"This will create files in '{FLAC_OUTPUT_DIR}' and create/overwrite the '{MANIFEST_TABLE_NAME}' table. Continue? (y/N): ")
    if response.lower() != 'y':
        print("Aborted.")
        return

    # Initialize the database table before starting generation
    init_manifest_db()
    
    manifest_entries = []
    for clip in tqdm(clips, desc="Generating FLAC files"):
        try:
            # 1. Construct the new, hierarchical output path
            vehicle = clip['vehicle_type'].replace(' ', '_').replace('/', '-')
            action = clip['action']
            location = clip['location']
            sensor = clip['target_sensor']
            
            # --- THIS IS THE NEW HIERARCHY ---
            output_dir = os.path.join(FLAC_OUTPUT_DIR, vehicle, action, location, sensor)
            os.makedirs(output_dir, exist_ok=True)
            
            # Create a unique filename
            ts_str = clip['clip_start_utc'].strftime('%Y%m%d_%H%M%S_%f')
            filename = f"event_{clip['original_annotation_id'][:8]}_{ts_str}.flac"
            output_path = os.path.join(output_dir, filename)

            # 2. Query raw audio data from QuestDB
            samples = questdb_client.query_raw_audio_data(
                clip['target_sensor'],
                clip['clip_start_utc'].isoformat(),
                clip['clip_end_utc'].isoformat()
            )

            if samples.size == 0:
                continue

            # 3. Write to FLAC file
            sf.write(output_path, samples, samplerate=SAMPLE_RATE, format='FLAC')

            # 4. Prepare the entry for the manifest database
            manifest_entries.append((
                clip['original_annotation_id'],
                clip['vehicle_type'],
                clip['action'],
                clip['location'],
                clip['target_sensor'], # Changed from 'sensor' to 'target_sensor' for clarity
                clip['clip_start_utc'].isoformat(),
                clip['clip_end_utc'].isoformat(),
                CLIP_DURATION_S,
                os.path.abspath(output_path),
                filename
            ))

        except Exception as e:
            print(f"\nERROR processing clip for event {clip['original_annotation_id'][:8]}: {e}")
            
    # 5. After the loop, perform a bulk insert into the manifest table
    if manifest_entries:
        print(f"\nWriting {len(manifest_entries)} entries to the manifest database...")
        with sqlite3.connect(DATABASE_FILE) as conn:
            cursor = conn.cursor()
            cursor.executemany(f"""
                INSERT INTO {MANIFEST_TABLE_NAME}
                (original_annotation_id, vehicle_type, action, location, sensor,
                 clip_start_utc, clip_end_utc, duration_seconds, file_path, file_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, manifest_entries)
        print("Manifest updated successfully.")

    print("\n--- Generation Complete ---")
    print(f"Successfully generated {len(manifest_entries)} audio clips in '{FLAC_OUTPUT_DIR}'.")
    print(f"The '{MANIFEST_TABLE_NAME}' table in '{DATABASE_FILE}' has been populated.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="ML Dataset Preparation Toolkit.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "mode",
        choices=["analyze", "generate"],
        help=(
            "Choose the operating mode:\n"
            "  analyze   - Perform a 'dry run' to evaluate the dataset balance. VERIFIES data in QuestDB first.\n"
            "  generate  - Create the actual .flac audio files and the database manifest."
        )
    )
    args = parser.parse_args()

    all_clips = get_all_potential_clips()
    
    if all_clips is not None:
        if args.mode == "analyze":
            run_analysis(all_clips)
        elif args.mode == "generate":
            run_generation(all_clips)