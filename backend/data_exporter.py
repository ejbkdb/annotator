# backend/data_exporter.py
import os
import csv
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Generator, Optional, List, Dict, Any
import click
import numpy as np
import soundfile as sf
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Text

from backend.pipeline_config import PipelineConfig, SensorGroup
from backend import questdb_client

# --- SQLAlchemy ORM Models ---
# Based on your project's schema to ensure type-safe and clear database interactions.
Base = declarative_base()

class Event(Base):
    __tablename__ = 'events'
    id = Column(String, primary_key=True)
    start_timestamp = Column(DateTime, nullable=False)
    end_timestamp = Column(DateTime, nullable=False)
    vehicle_type = Column(String, nullable=False)
    vehicle_identifier = Column(String)
    direction = Column(String)
    annotator_notes = Column(Text)
    status = Column(String, nullable=False, default='manual')
    convoy_id = Column(String, ForeignKey('convoys.id'))
    vehicle_action = Column(String, default='driveby')

class RefinedAnnotation(Base):
    __tablename__ = 'refined_annotations'
    id = Column(String, primary_key=True)
    parent_event_id = Column(String, nullable=False)
    source_collection = Column(String, nullable=False)
    start_timestamp = Column(DateTime, nullable=False)
    end_timestamp = Column(DateTime, nullable=False)
    vehicle_type = Column(String, nullable=False)
    vehicle_subclass = Column(String, nullable=False)
    location = Column(String, nullable=False)
    action = Column(String, nullable=False)
    direction = Column(String, nullable=False)
    annotator_notes = Column(Text)

class Convoy(Base):
    __tablename__ = 'convoys'
    id = Column(String, primary_key=True)
    convoy_number = Column(String, nullable=False)
    direction = Column(String, nullable=False)
    notes = Column(Text)
    convoy_spacing_seconds = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

# --- Configuration & Setup ---
# Your existing database.py points to two different files. I'm using a generic name.
# Ensure ANNOTATOR_DB_URL points to the correct one (e.g., test_range.db).
DATABASE_URL = os.environ.get("ANNOTATOR_DB_URL", "sqlite:///./test_range.db")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def setup_logging(output_dir: Path, log_filename: str):
    """Sets up logging to both console and a file in the output directory."""
    log_dir = output_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / log_filename
    
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[logging.FileHandler(log_file), logging.StreamHandler()]
    )
    logging.info(f"Logging initialized. Log file at: {log_file}")

def get_db_session() -> Session:
    """Provides a SQLAlchemy session."""
    return SessionLocal()

def sanitize_for_path(value: Any, fallback: str = 'unknown') -> str:
    """Sanitizes a string to be safe for a directory or filename."""
    if not value or not isinstance(value, str):
        return fallback
    return value.strip().replace(' ', '_').replace('/', '-').replace('\\', '-')

def create_sensor_group_map(groups: List[SensorGroup]) -> Dict[str, List[str]]:
    """Creates a lookup map from a collection to its sibling collections."""
    collection_to_siblings = {}
    for group in groups:
        for collection in group.collections:
            siblings = [c for c in group.collections if c != collection]
            collection_to_siblings[collection] = siblings
    return collection_to_siblings

def generate_windows(start_time: datetime, end_time: datetime, chunk_duration_s: float, overlap_s: float) -> Generator[tuple[datetime, datetime], None, None]:
    """Yields start and end timestamps for each chunk, ensuring no overrun."""
    step_s = chunk_duration_s - overlap_s
    if step_s <= 0:
        raise ValueError("Overlap must be less than chunk duration.")
    current_start = start_time
    duration_delta = timedelta(seconds=chunk_duration_s)
    step_delta = timedelta(seconds=step_s)
    while current_start + duration_delta <= end_time:
        yield current_start, current_start + duration_delta
        current_start += step_delta

def save_audio_clip(output_path: Path, audio_data: np.ndarray, sample_rate: int, format: str):
    """Saves a numpy audio array to a file."""
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(output_path), audio_data, samplerate=sample_rate, format=format.upper())
    except Exception as e:
        logging.error(f"Failed to write audio file to {output_path}: {e}")
        raise

@click.group()
def export():
    """A unified CLI tool for exporting annotated audio data."""
    pass

@export.command(name="model-training")
@click.option('--config', 'config_path', required=True, type=click.Path(exists=True, dir_okay=False), help='Path to pipeline config for sensor groups and alignment.')
@click.option('--output-dir', required=True, type=click.Path(file_okay=False), help='Directory to save exported data.')
@click.option('--format', type=click.Choice(['flac', 'wav'], case_sensitive=False), default='flac', show_default=True)
@click.option('--duration', type=float, required=True, help='Duration of each audio clip in seconds.')
@click.option('--overlap', type=float, required=True, help='Overlap between clips in seconds.')
def export_model_training(config_path: str, output_dir: str, format: str, duration: float, overlap: float):
    """
    Exports chunked audio from refined_annotations for model training.

    This command uses sensor group definitions to propagate a single annotation
    across all sensors at the same location, creating a richer dataset.
    """
    output_path = Path(output_dir)
    run_id = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    setup_logging(output_path, f"export_model_training_{run_id}.log")
    
    logging.info("--- Starting Model Training Data Export (with Sensor Grouping) ---")
    
    try:
        config = PipelineConfig.from_json(config_path)
        logging.info(f"Loaded pipeline config '{config.pipeline_id}'.")
    except Exception as e:
        logging.error(f"Failed to load or parse pipeline config: {e}")
        return

    sensor_group_map = create_sensor_group_map(config.groups)
    if not sensor_group_map:
        logging.warning("No sensor groups defined in config. Will only export from explicitly annotated collections.")
    else:
        logging.info(f"Loaded {len(config.groups)} sensor groups for annotation propagation.")

    db = get_db_session()
    annotations = db.query(RefinedAnnotation).order_by(RefinedAnnotation.start_timestamp).all()
    logging.info(f"Found {len(annotations)} refined annotations to process.")

    manifest_data = []
    clips_created, clips_skipped = 0, 0

    for ann in annotations:
        ann_duration_s = (ann.end_timestamp - ann.start_timestamp).total_seconds()
        
        if ann_duration_s < duration:
            logging.warning(f"SKIPPING Annotation ID {ann.id[:8]} (on {ann.source_collection}): Duration ({ann_duration_s:.2f}s) < target ({duration}s).")
            clips_skipped += 1
            continue

        annotated_collection = ann.source_collection
        sibling_collections = sensor_group_map.get(annotated_collection, [])
        collections_to_process = [annotated_collection] + sibling_collections

        if len(collections_to_process) > 1:
            logging.info(f"Annotation {ann.id[:8]} on '{annotated_collection}' will be propagated to {len(sibling_collections)} other sensors.")

        for target_collection in collections_to_process:
            for clip_start, clip_end in generate_windows(ann.start_timestamp, ann.end_timestamp, duration, overlap):
                offset_ms = config.alignment.offsets.get(target_collection, 0)
                time_delta = timedelta(milliseconds=offset_ms)
                adjusted_start, adjusted_end = clip_start - time_delta, clip_end - time_delta

                try:
                    audio_data = questdb_client.query_raw_audio_data(
                        collection=target_collection,
                        start=adjusted_start.isoformat(),
                        end=adjusted_end.isoformat()
                    )

                    if audio_data.size == 0:
                        logging.warning(f"No audio for annotation {ann.id[:8]} in target collection '{target_collection}' for window {clip_start.isoformat()}.")
                        continue

                    base_dir = output_path / "model_training_clips" / sanitize_for_path(ann.location) / sanitize_for_path(ann.vehicle_type) / sanitize_for_path(ann.action) / sanitize_for_path(ann.direction)
                    ts_str = clip_start.strftime('%Y%m%dT%H%M%S%f')[:-3]
                    clip_filename = f"{ann.id[:8]}_{target_collection}_{ts_str}.{format}"
                    clip_output_path = base_dir / clip_filename

                    save_audio_clip(clip_output_path, audio_data, config.processing.target_sample_rate, format)
                    clips_created += 1

                    manifest_data.append({
                        "clip_path": str(clip_output_path.relative_to(output_path)),
                        "source_annotation_id": ann.id,
                        "annotated_collection": annotated_collection,
                        "audio_source_collection": target_collection,
                        "clip_start_utc": clip_start.isoformat(),
                        "clip_end_utc": clip_end.isoformat(),
                        "duration_s": duration, "vehicle_type": ann.vehicle_type,
                        "vehicle_subclass": ann.vehicle_subclass, "action": ann.action,
                        "location": ann.location, "direction": ann.direction,
                    })
                except Exception as e:
                    logging.error(f"Failed to process clip for ann {ann.id[:8]} on target {target_collection}: {e}")

    manifest_path = output_path / "manifest.csv"
    if manifest_data:
        logging.info(f"Writing {len(manifest_data)} entries to manifest: {manifest_path}")
        with open(manifest_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=manifest_data[0].keys())
            writer.writeheader()
            writer.writerows(manifest_data)
    
    logging.info(f"--- Model Training Export Complete ---")
    logging.info(f"Clips Created: {clips_created} | Annotations Skipped: {clips_skipped}")
    db.close()

# Note: The logic for single-vehicle and convoy exports remains unchanged as their purpose
# is to extract raw time blocks, not propagate fine-grained annotations. They are included
# here for completeness of the unified tool.
def _export_event_or_convoy(db: Session, output_path: Path, format: str, chunked: bool, duration: Optional[float], overlap: Optional[float], start_time: datetime, end_time: datetime, metadata: Dict[str, Any], export_type: str, base_id: str):
    """Shared logic to export audio for an event or convoy."""
    all_collections = questdb_client.get_collections()
    relevant_collections = [c for c in all_collections if questdb_client.check_data_exists(c, start_time.isoformat(), end_time.isoformat())]
    if not relevant_collections:
        logging.warning(f"No data found in any collection for {export_type} {base_id}. Skipping.")
        return 0
    logging.info(f"Found data in collections: {relevant_collections} for {export_type} {base_id}")
    clips_created = 0
    base_dir = (output_path / export_type / sanitize_for_path(metadata.get('location')) / sanitize_for_path(metadata.get('vehicle_type')) / sanitize_for_path(metadata.get('action')) / sanitize_for_path(metadata.get('direction')) / base_id[:8])
    for collection in relevant_collections:
        try:
            full_audio = questdb_client.query_raw_audio_data(collection, start_time.isoformat(), end_time.isoformat())
            if full_audio.size > 0:
                full_path = base_dir / f"{collection}_full.{format}"
                save_audio_clip(full_path, full_audio, 48000, format)
                logging.info(f"Saved full-length clip: {full_path}")
                clips_created += 1
        except Exception as e:
            logging.error(f"Could not save full-length clip for {collection}: {e}")
        if chunked:
            for clip_start, clip_end in generate_windows(start_time, end_time, duration, overlap):
                try:
                    chunk_audio = questdb_client.query_raw_audio_data(collection, clip_start.isoformat(), clip_end.isoformat())
                    if chunk_audio.size > 0:
                        ts_str = clip_start.strftime('%Y%m%dT%H%M%S%f')[:-3]
                        chunk_filename = f"{collection}_{ts_str}.{format}"
                        chunk_path = base_dir / "chunks" / chunk_filename
                        save_audio_clip(chunk_path, chunk_audio, 48000, format)
                        clips_created += 1
                except Exception as e:
                    logging.error(f"Could not save chunk for {collection} at {clip_start}: {e}")
    return clips_created

@export.command(name="single-vehicle")
@click.option('--output-dir', required=True, type=click.Path(file_okay=False))
@click.option('--format', type=click.Choice(['flac', 'wav'], case_sensitive=False), default='wav', show_default=True)
@click.option('--chunked', is_flag=True, default=False, show_default=True)
@click.option('--duration', type=float, default=5.0, show_default=True)
@click.option('--overlap', type=float, default=2.5, show_default=True)
def export_single_vehicle(output_dir: str, format: str, chunked: bool, duration: float, overlap: float):
    """Exports audio for single-vehicle events (not part of a convoy)."""
    output_path = Path(output_dir)
    run_id = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    setup_logging(output_path, f"export_single_vehicle_{run_id}.log")
    logging.info("--- Starting Single-Vehicle Data Export ---")
    db = get_db_session()
    events = db.query(Event).filter(Event.convoy_id.is_(None)).all()
    logging.info(f"Found {len(events)} single-vehicle events.")
    total_clips = 0
    for event in events:
        metadata = {'location': 'unknown', 'vehicle_type': event.vehicle_type, 'action': event.vehicle_action, 'direction': event.direction}
        total_clips += _export_event_or_convoy(db, output_path, format, chunked, duration, overlap, event.start_timestamp, event.end_timestamp, metadata, "single_vehicle_runs", event.id)
    logging.info(f"--- Single-Vehicle Export Complete --- \nTotal files created: {total_clips}")
    db.close()

@export.command(name="convoy")
@click.option('--output-dir', required=True, type=click.Path(file_okay=False))
@click.option('--format', type=click.Choice(['flac', 'wav'], case_sensitive=False), default='flac', show_default=True)
@click.option('--convoy-id', 'specific_convoy_id', type=str, default=None)
@click.option('--chunked', is_flag=True, default=False, show_default=True)
@click.option('--duration', type=float, default=5.0, show_default=True)
@click.option('--overlap', type=float, default=2.5, show_default=True)
def export_convoy(output_dir: str, format: str, specific_convoy_id: Optional[str], chunked: bool, duration: float, overlap: float):
    """Exports audio for entire convoys by aggregating event times."""
    output_path = Path(output_dir)
    run_id = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    setup_logging(output_path, f"export_convoy_{run_id}.log")
    logging.info("--- Starting Convoy Data Export ---")
    db = get_db_session()
    query = db.query(Convoy)
    if specific_convoy_id:
        query = query.filter(Convoy.id == specific_convoy_id)
    convoys = query.all()
    logging.info(f"Found {len(convoys)} convoys to process.")
    total_clips = 0
    for convoy in convoys:
        result = db.execute(text("SELECT MIN(start_timestamp), MAX(end_timestamp) FROM events WHERE convoy_id = :cid"), {'cid': convoy.id}).fetchone()
        if not result or not result[0]:
            logging.warning(f"Convoy {convoy.id} has no events. Skipping.")
            continue
        convoy_start, convoy_end = result
        metadata = {'location': 'convoy_run', 'vehicle_type': f"convoy_{convoy.convoy_number}", 'action': 'convoy', 'direction': convoy.direction}
        total_clips += _export_event_or_convoy(db, output_path, format, chunked, duration, overlap, convoy_start, convoy_end, metadata, "convoy_runs", convoy.id)
    logging.info(f"--- Convoy Export Complete --- \nTotal files created: {total_clips}")
    db.close()

if __name__ == '__main__':
    from multiprocessing import freeze_support
    freeze_support()
    export()