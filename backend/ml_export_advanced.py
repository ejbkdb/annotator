# backend/ml_export_advanced.py
import os
import csv
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from sqlalchemy.orm import Session
# IMPLEMENTATION: Import soundfile for real audio writing
import soundfile as sf
import numpy as np

from .pipeline_config import PipelineConfig
# IMPLEMENTATION: Import SQLAlchemy models from the new location
from .models_sqlalchemy import Annotation 
# IMPLEMENTATION: Import the actual QuestDB client
from . import questdb_client 

if not logging.getLogger().hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_last_export_timestamp(manifest_path: Path) -> Optional[datetime]:
    """Reads the manifest to find the timestamp of the last exported event."""
    if not manifest_path.exists():
        return None
    last_ts = None
    try:
        # IMPLEMENTATION: Real file reading
        with open(manifest_path, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # IMPLEMENTATION: Robust timestamp parsing, ensuring UTC awareness
                ts_str = row.get('event_end_utc')
                if not ts_str: continue
                
                try:
                    # Handles 'Z' or explicit offsets correctly
                    ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                except ValueError:
                    logging.warning(f"Skipping row with invalid timestamp format: {ts_str}")
                    continue
                
                if last_ts is None or ts > last_ts:
                    last_ts = ts
    except Exception as e:
        logging.error(f"Error reading manifest file at {manifest_path}: {e}")
        return None
        
    return last_ts

def export_data(config: PipelineConfig, session: Session, incremental: bool = True):
    """Exports annotated data into an ML-ready format."""
    logging.info(f"Starting ML export for pipeline: {config.pipeline_id}. Incremental: {incremental}")
    
    # IMPLEMENTATION: Ensure output directory exists (Real FS operation)
    try:
        output_base_dir = Path(config.output.base_directory)
        output_base_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logging.error(f"Invalid output directory configuration or permission error: {e}")
        return
    
    manifest_path = output_base_dir / "manifest.csv"
    
    start_time = None
    if incremental:
        start_time = get_last_export_timestamp(manifest_path)
        if start_time:
            logging.info(f"Incremental export enabled. Exporting events after: {start_time.isoformat()}")

    # IMPLEMENTATION: Query actual annotations from DB using SQLAlchemy
    query = session.query(Annotation)
    
    # Filter by sensors defined in the pipeline config
    query = query.filter(Annotation.sensor.in_(config.input.collections))
    
    if start_time:
        # Only export annotations that ended after the last exported timestamp
        query = query.filter(Annotation.end_timestamp > start_time)
        
    new_annotations = query.order_by(Annotation.start_timestamp).all()

    if not new_annotations:
        logging.info("No new annotations to export.")
        return

    logging.info(f"Found {len(new_annotations)} annotations to export.")
    
    # Determine write mode for the manifest
    # 'a' for append (incremental), 'w' for write (full export or new file)
    write_mode = 'a' if incremental and manifest_path.exists() else 'w'
    
    try:
        # IMPLEMENTATION: Real CSV file writing
        with open(manifest_path, write_mode, newline='') as f:
            fieldnames = [
                'clip_id', 'source_annotation_id', 'event_start_utc', 'event_end_utc', 
                'clip_start_utc', 'clip_end_utc', 'duration_s', 'sensor', 'file_path', 
                'vehicle_type', 'action', 'location'
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            
            # Write header if it's a new file or if we are overwriting
            if write_mode == 'w' or (write_mode == 'a' and manifest_path.stat().st_size == 0):
                writer.writeheader()

            for ann in new_annotations:
                # Ensure timestamps are timezone-aware (assuming DB stores them as naive UTC or already aware)
                ann_start = ann.start_timestamp.replace(tzinfo=timezone.utc) if ann.start_timestamp.tzinfo is None else ann.start_timestamp
                ann_end = ann.end_timestamp.replace(tzinfo=timezone.utc) if ann.end_timestamp.tzinfo is None else ann.end_timestamp

                # Generate windows based on config
                window_size = timedelta(seconds=config.processing.window_size_seconds)
                step_size = timedelta(seconds=config.processing.window_size_seconds - config.processing.overlap_seconds)
                
                current_start = ann_start
                while current_start + window_size <= ann_end:
                    clip_start = current_start
                    clip_end = current_start + window_size
                    
                    # 1. Fetch audio from QuestDB (REAL IMPLEMENTATION)
                    try:
                        audio_samples = questdb_client.query_raw_audio_data(
                            ann.sensor, 
                            clip_start.isoformat(), 
                            clip_end.isoformat()
                        )
                    except Exception as e:
                        logging.error(f"Failed to fetch audio for annotation {ann.id} clip {clip_start}: {e}")
                        current_start += step_size
                        continue

                    if audio_samples.size == 0:
                        logging.warning(f"No audio data returned for annotation {ann.id} clip {clip_start}.")
                        current_start += step_size
                        continue
                        
                    # 2. Create directory structure (REAL IMPLEMENTATION)
                    try:
                        # Use .format() based on the pipeline config structure definition
                        dir_structure = config.output.structure.format(
                            vehicle_type=ann.vehicle_type or 'unknown',
                            action=ann.action or 'unknown',
                            location=ann.location or 'unknown',
                            sensor=ann.sensor or 'unknown'
                        )
                        # Sanitize directory paths
                        dir_structure = dir_structure.replace(' ', '_').replace('/', os.sep)
                        output_dir = output_base_dir / dir_structure
                        output_dir.mkdir(parents=True, exist_ok=True)
                    except Exception as e:
                        logging.error(f"Error creating directory structure for {ann.id}: {e}")
                        continue
                    
                    # 3. Create file path
                    # Unique ID based on annotation ID and precise start time
                    clip_id = f"{ann.id[:8]}_{clip_start.strftime('%Y%m%d%H%M%S%f')}"
                    file_extension = config.output.format.lower()
                    file_path = output_dir / f"{clip_id}.{file_extension}"
                    
                    # 4. Save audio file (REAL IMPLEMENTATION)
                    try:
                        # Use soundfile to write the numpy array to the specified format (FLAC/WAV)
                        sf.write(str(file_path), audio_samples, config.processing.target_sample_rate, format=file_extension.upper())
                    except Exception as e:
                        logging.error(f"Failed to write audio file {file_path}: {e}")
                        continue
                    
                    # 5. Write manifest entry
                    writer.writerow({
                        'clip_id': clip_id,
                        'source_annotation_id': ann.id,
                        'event_start_utc': ann_start.isoformat(),
                        'event_end_utc': ann_end.isoformat(),
                        'clip_start_utc': clip_start.isoformat(),
                        'clip_end_utc': clip_end.isoformat(),
                        'duration_s': config.processing.window_size_seconds,
                        'sensor': ann.sensor,
                        # Store relative path in the manifest
                        'file_path': str(file_path.relative_to(output_base_dir)),
                        'vehicle_type': ann.vehicle_type,
                        'action': ann.action,
                        'location': ann.location
                    })
                    
                    current_start += step_size
                    
    except IOError as e:
        # Handle disk full, permissions errors, etc.
        logging.error(f"File I/O error during export (e.g., manifest writing or disk access): {e}")

    logging.info(f"Export complete. Manifest updated at {manifest_path}")
