
# analyze_rev_events.py
import sqlite3
import json
import os
from datetime import datetime
from collections import defaultdict
import numpy as np
import matplotlib
matplotlib.use('Agg') # Use a non-interactive backend for saving files
import matplotlib.pyplot as plt

# This import assumes you run the script from the project's root directory
from backend import questdb_client

# --- CONFIGURATION ---
DATABASE_FILE = "/home/eborcherding/Documents/annotator/flv2.db"
# --- THIS IS THE FIX: Point to the new, correct table ---
CORRECTED_TABLE_NAME = "corrected_annotations"
ANALYSIS_OUTPUT_DIR = "v2analysis_plots"
SAMPLE_RATE = 48000 # Your audio sample rate
# ---------------------

def analyze_rev_events_alignment():
    """
    Analyzes 'rev' events by querying the lookup table and fetching
    time-corrected audio data from QuestDB to generate comparison plots.
    """
    print("--- Starting: 'Rev' Event Alignment Analysis ---")
    
    try:
        import matplotlib.pyplot
    except ImportError:
        print("\nFATAL ERROR: The 'matplotlib' library is required. Please run: pip install matplotlib")
        return

    os.makedirs(ANALYSIS_OUTPUT_DIR, exist_ok=True)
    print(f"Analysis plots will be saved to '{ANALYSIS_OUTPUT_DIR}/'")

    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Query is now simpler as it targets the lookup table directly.
    # We group by the original annotation ID to get all sensor views of a single event.
    query = f"""
        SELECT * FROM {CORRECTED_TABLE_NAME}
        WHERE action = 'driveby' AND original_annotation_id IN (
            SELECT original_annotation_id FROM {CORRECTED_TABLE_NAME}
            WHERE action = 'driveby'
            GROUP BY original_annotation_id
            HAVING COUNT(target_sensor) > 1
        )
        ORDER BY original_annotation_id, target_sensor;
    """
    try:
        cursor.execute(query)
        rev_events = cursor.fetchall()
    except sqlite3.OperationalError:
        print(f"\nFATAL ERROR: The table '{CORRECTED_TABLE_NAME}' does not exist.")
        print("Please run 'apply_time_offsets.py' first to generate the corrected data.")
        conn.close()
        return
        
    if not rev_events:
        print("No suitable 'rev' events found for comparison.")
        conn.close()
        return
    print(f"Found {len(rev_events)} lookup rows for comparable 'rev' events.")

    grouped_events = defaultdict(list)
    for event in rev_events:
        grouped_events[event['original_annotation_id']].append(dict(event))

    print(f"\nProcessing {len(grouped_events)} unique 'rev' events for plot generation...")

    for ann_id, events_in_group in grouped_events.items():
        print(f"\n--- Analyzing Event: {ann_id[:8]} ---")
        
        audio_data = {}
        overall_min_start_time = None
        overall_max_end_time = None

        for event in events_in_group:
            sensor = event['target_sensor']
            start_iso = event['corrected_start_utc']
            end_iso = event['corrected_end_utc']
            print(f"  Fetching data for sensor '{sensor}'...")

            try:
                samples = questdb_client.query_raw_audio_data(sensor, start_iso, end_iso)
                if samples.size > 0:
                    start_ts = datetime.fromisoformat(start_iso)
                    end_ts = datetime.fromisoformat(end_iso)
                    audio_data[sensor] = {
                        "samples": samples, "start_ts": start_ts, "end_ts": end_ts,
                        "location": event['location']
                    }
                    if overall_min_start_time is None or start_ts < overall_min_start_time:
                        overall_min_start_time = start_ts
                    if overall_max_end_time is None or end_ts > overall_max_end_time:
                        overall_max_end_time = end_ts
                else:
                    print(f"    WARNING: No audio data returned for {sensor} in the specified time range.")
            except Exception as e:
                print(f"    ERROR fetching QuestDB data for {sensor}: {e}")

        if len(audio_data) < 2:
            print("  Skipping plot: Less than two sensors returned data for this event.")
            continue

        num_sensors = len(audio_data)
        fig, axes = plt.subplots(num_sensors, 1, figsize=(20, num_sensors * 4), sharex=True, squeeze=False)
        axes = axes.flatten()
        
        fig.suptitle(f"Time-Aligned 'Rev' Event Analysis\nOriginal Annotation ID: {ann_id}", fontsize=16)

        # for i, (sensor, data) in enumerate(audio_data.items()):
        #     ax = axes[i]
        #     time_offset = (data["start_ts"] - overall_min_start_time).total_seconds()
        #     duration_sec = len(data["samples"]) / SAMPLE_RATE
        #     time_axis = np.linspace(time_offset, time_offset + duration_sec, num=len(data["samples"]))
        # Instead of complex time alignment, just do:
        for i, (sensor, data) in enumerate(audio_data.items()):
            ax = axes[i]
            # Simple sample-based x-axis (no datetime calculations needed)
            time_axis = np.arange(len(data["samples"])) / SAMPLE_RATE
            ax.plot(time_axis, data["samples"])
            ax.set_title(f"Sensor: {sensor} - Location: {data['location']}")    
            ax.plot(time_axis, data["samples"], label=f"Location: {data['location']}")
            ax.set_title(f"Sensor: {sensor}")
            ax.set_ylabel("Amplitude")
            ax.grid(True, linestyle='--', alpha=0.6)
            ax.legend(loc='upper right')
        
        total_duration = (overall_max_end_time - overall_min_start_time).total_seconds()
        axes[-1].set_xlabel("Time (seconds) from First Corrected Timestamp")
        axes[0].set_xlim(0, total_duration)

        plt.tight_layout(rect=[0, 0.03, 1, 0.95])
        
        plot_filename = os.path.join(ANALYSIS_OUTPUT_DIR, f"rev_analysis_{ann_id[:8]}.png")
        plt.savefig(plot_filename)
        plt.close(fig)
        print(f"  ✓ Plot saved successfully to {plot_filename}")

    conn.close()

if __name__ == "__main__":
    analyze_rev_events_alignment()