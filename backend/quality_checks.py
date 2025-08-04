# backend/quality_checks.py
import os
import json
import logging
import csv
from pathlib import Path
import numpy as np
import soundfile as sf

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- QA Thresholds ---
SILENCE_THRESHOLD_RMS = 0.005  # RMS value below which audio is considered silent
DURATION_TOLERANCE_S = 0.1   # Allowed deviation from expected clip duration
ALIGNMENT_TOLERANCE_MS = 500 # Max allowed time difference between sensors for the same event

def validate_duration(file_path: Path, expected_duration_s: float, sample_rate: int) -> tuple[bool, str]:
    """Checks if the audio file's duration is within tolerance."""
    try:
        frames = sf.info(str(file_path)).frames
        actual_duration_s = frames / sample_rate
        if abs(actual_duration_s - expected_duration_s) > DURATION_TOLERANCE_S:
            return False, f"Duration mismatch: expected {expected_duration_s:.2f}s, got {actual_duration_s:.2f}s"
        return True, ""
    except Exception as e:
        return False, f"Could not read file info: {e}"

def detect_silence_or_corruption(file_path: Path) -> tuple[bool, str]:
    """Checks for silence or basic corruption (e.g., all zeros)."""
    try:
        audio, _ = sf.read(str(file_path), dtype='float32')
        if not np.any(audio):
            return False, "File is completely silent (all zeros)."
        
        rms = np.sqrt(np.mean(audio**2))
        if rms < SILENCE_THRESHOLD_RMS:
            return False, f"File appears silent (RMS: {rms:.4f} < {SILENCE_THRESHOLD_RMS:.4f})."
        return True, ""
    except Exception as e:
        return False, f"Failed to read or analyze audio data: {e}"

def check_alignment_tolerance(manifest_data: list) -> dict:
    """Checks if clips from the same event are aligned within a tolerance."""
    events = {}
    for row in manifest_data:
        ann_id = row['source_annotation_id']
        if ann_id not in events:
            events[ann_id] = []
        events[ann_id].append({
            'clip_id': row['clip_id'],
            'sensor': row['sensor'],
            'start_time': datetime.fromisoformat(row['clip_start_utc'])
        })

    failures = {}
    for ann_id, clips in events.items():
        if len(clips) < 2:
            continue
        
        start_times = [c['start_time'] for c in clips]
        max_delta = (max(start_times) - min(start_times)).total_seconds() * 1000 # in ms

        if max_delta > ALIGNMENT_TOLERANCE_MS:
            failures[ann_id] = f"Alignment tolerance exceeded: {max_delta:.0f}ms > {ALIGNMENT_TOLERANCE_MS}ms"
            
    return failures


def run_quality_checks(export_directory: str, manifest_path: str) -> dict:
    """
    Runs a suite of quality checks on an exported dataset.

    Args:
        export_directory: The base directory of the exported dataset.
        manifest_path: Path to the manifest.csv file.

    Returns:
        A dictionary containing the quality report.
    """
    logging.info(f"Starting quality checks on dataset in '{export_directory}'")
    base_dir = Path(export_directory)
    manifest_p = Path(manifest_path)

    if not manifest_p.exists():
        logging.error("Manifest file not found.")
        return {"error": "Manifest file not found."}

    report = {
        "summary": {"total_clips": 0, "failed_clips": 0},
        "duration_failures": [],
        "silence_corruption_failures": [],
        "alignment_failures": {},
        "file_not_found": []
    }

    manifest_data = []
    with open(manifest_p, 'r') as f:
        reader = csv.DictReader(f)
        manifest_data = list(reader)

    report["summary"]["total_clips"] = len(manifest_data)

    # Individual file checks
    for row in manifest_data:
        clip_failed = False
        file_path = base_dir / row['file_path']
        if not file_path.exists():
            report['file_not_found'].append(row['clip_id'])
            clip_failed = True
            continue

        # Duration Check
        is_valid, msg = validate_duration(file_path, float(row['duration_s']), 16000) # Assuming 16k SR
        if not is_valid:
            report['duration_failures'].append({'clip_id': row['clip_id'], 'reason': msg})
            clip_failed = True

        # Silence/Corruption Check
        is_valid, msg = detect_silence_or_corruption(file_path)
        if not is_valid:
            report['silence_corruption_failures'].append({'clip_id': row['clip_id'], 'reason': msg})
            clip_failed = True
        
        if clip_failed:
            report["summary"]["failed_clips"] += 1

    # Multi-file checks
    report['alignment_failures'] = check_alignment_tolerance(manifest_data)
    
    # Save report
    report_path = manifest_p.parent / "quality_report.json"
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
        
    logging.info(f"Quality checks complete. Report saved to {report_path}")
    return report