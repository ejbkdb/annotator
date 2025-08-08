# backend/data_exporter.py
# backend/data_exporter.py
import os
import csv
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any, Generator, Tuple
import click
import numpy as np
import soundfile as sf
from sqlalchemy import create_engine, text, inspect, func
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from sqlalchemy import Column, String, DateTime, Integer

from .export_config import ExportConfig, WindowingConfig, SensorGroup
from .audio_processor import AudioProcessor
from . import questdb_client
from .models_sqlalchemy import SensorMetadata

# --- Configuration & Setup ---

# Database setup (for annotations/events/metadata)
DATABASE_URL = os.environ.get("ANNOTATOR_DB_URL", "sqlite:///./annotation_system.db")

# Determine connection arguments based on DB type for SQLAlchemy
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

try:
    engine = create_engine(DATABASE_URL, connect_args=connect_args)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
except Exception as e:
    print(f"Warning: Could not initialize SQLAlchemy engine: {e}")
    engine = None
    SessionLocal = None

# Set up the AudioProcessor instance for potential resampling
try:
    audio_processor = AudioProcessor()
except Exception as e:
    print(f"Warning: Could not initialize AudioProcessor: {e}")
    audio_processor = None

# --- SQLAlchemy ORM Models (Required for querying source tables) ---
Base = declarative_base()

# Define models explicitly for the known source tables. This provides robustness and clarity.

class Event(Base):
    # Represents the 'events' table (often used for single_vehicle and convoy sources)
    __tablename__ = 'events'
    __table_args__ = {'extend_existing': True} # Handle potential re-definition if modules are reloaded
    id = Column(String, primary_key=True)
    start_timestamp = Column(DateTime, nullable=False)
    end_timestamp = Column(DateTime, nullable=False)
    vehicle_type = Column(String)
    vehicle_action = Column(String) # Specific to 'events' table
    direction = Column(String)
    convoy_id = Column(String)
    status = Column(String)
    # Note: 'events' table often lacks explicit sensor/location links in the basic schema

class RefinedAnnotation(Base):
    # Represents the 'refined_annotations' table (often used for model_training)
    __tablename__ = 'refined_annotations'
    __table_args__ = {'extend_existing': True}
    id = Column(String, primary_key=True)
    source_collection = Column(String, nullable=False) # Crucial link to sensor
    start_timestamp = Column(DateTime, nullable=False)
    end_timestamp = Column(DateTime, nullable=False)
    vehicle_type = Column(String)
    action = Column(String)
    location = Column(String)
    direction = Column(String)

class Annotation(Base):
    # Represents the advanced 'annotations' table (from models_sqlalchemy.py)
    __tablename__ = 'annotations'
    __table_args__ = {'extend_existing': True}
    id = Column(String, primary_key=True)
    sensor = Column(String, nullable=False) # Crucial link to sensor
    start_timestamp = Column(DateTime, nullable=False)
    end_timestamp = Column(DateTime, nullable=False)
    vehicle_type = Column(String)
    action = Column(String)
    location = Column(String)
    status = Column(String)


# Mapping config names to SQLAlchemy models
TABLE_MODEL_MAP = {
    "refined_annotations": RefinedAnnotation,
    "events": Event,
    "annotations": Annotation
}

# --- Helper Functions ---

def setup_logging(output_dir: Path, log_filename: str):
    """Sets up logging to both console and a file."""
    log_dir = output_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / log_filename
    
    # Reset root logger handlers to prevent duplicate logs if run multiple times
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
    if SessionLocal:
        return SessionLocal()
    raise RuntimeError("Database session factory (SessionLocal) is not initialized.")

def sanitize_for_path(value: Any, fallback: str = 'unknown') -> str:
    """Sanitizes a string to be safe for a directory or filename."""
    if value is None:
        return fallback
    s_value = str(value).strip()
    if not s_value:
        return fallback
    # Remove characters unsafe for most filesystems
    return s_value.replace(' ', '_').replace('/', '-').replace('\\', '-').replace(':', '').replace('.', '_')

def create_group_maps(groups: List[SensorGroup]) -> tuple[Dict[str, str], Dict[str, SensorGroup]]:
    """Creates lookup maps: sensor -> group_name and group_name -> group_object."""
    sensor_to_group_name = {}
    group_name_to_object = {}
    for group in groups:
        group_name_to_object[group.name] = group
        for collection in group.collections:
            if collection in sensor_to_group_name:
                logging.warning(f"Sensor '{collection}' appears in multiple groups. Using the last one defined ('{group.name}').")
            sensor_to_group_name[collection] = group.name
    return sensor_to_group_name, group_name_to_object

def generate_windows(start_time: datetime, end_time: datetime, window_config: WindowingConfig) -> Generator[tuple[datetime, datetime], None, None]:
    """Yields start and end timestamps for each chunk, ensuring exact window size."""
    chunk_duration_s = window_config.window_size_seconds
    overlap_s = window_config.overlap_seconds
    step_s = chunk_duration_s - overlap_s # Guaranteed > 0 by validation
    
    current_start = start_time
    duration_delta = timedelta(seconds=chunk_duration_s)
    step_delta = timedelta(seconds=step_s)
    
    # Only yield windows that fit entirely within the event boundaries
    while current_start + duration_delta <= end_time:
        yield current_start, current_start + duration_delta
        current_start += step_delta

def generate_windows_with_final_capture(start_time: datetime, end_time: datetime, window_config: WindowingConfig):
    """Generates windows with pre-boundary final window to avoid data loss."""
    windows = list(generate_windows(start_time, end_time, window_config))  # Current logic
    
    if windows:
        last_window_end = windows[-1][1]
        remaining_duration = (end_time - last_window_end).total_seconds()
        
        # If there's significant remaining data, create an overlapping final window
        if remaining_duration > window_config.window_size_seconds * 0.3:  # 30% threshold
            final_start = end_time - timedelta(seconds=window_config.window_size_seconds)
            if final_start > windows[-1][0]:  # Avoid duplicate
                windows.append((final_start, end_time))
    
    return windows

def get_sensor_sample_rate(db: Session, collection_name: str) -> int:
    """Retrieves the sample rate from metadata, falling back to a default if not found."""
    DEFAULT_SR = 48000
    try:
        # Check if SensorMetadata is properly mapped and the table exists in the current engine context
        if engine and inspect(engine).has_table(SensorMetadata.__tablename__):
            metadata = db.query(SensorMetadata).filter_by(collection_name=collection_name).first()
            if metadata and metadata.sample_rate:
                return metadata.sample_rate
    except Exception as e:
        # Handle potential SQLAlchemy errors or reflection issues
        logging.warning(f"Could not query SensorMetadata: {e}. Falling back to default.")

    logging.info(f"Sample rate metadata unavailable for '{collection_name}'. Falling back to default: {DEFAULT_SR}Hz.")
    return DEFAULT_SR

def fetch_and_process_audio(db: Session, collection: str, start: datetime, end: datetime, target_sr_config: Optional[int]) -> Tuple[Optional[np.ndarray], int]:
    """Fetches audio from QuestDB, determines sample rate, and optionally resamples it."""
    if not questdb_client or not audio_processor:
        logging.error("Missing required clients (QuestDB or AudioProcessor). Cannot fetch/process audio.")
        return None, 0
        
    try:
        # 1. Fetch raw data (questdb_client returns int16)
        audio_data = questdb_client.query_raw_audio_data(collection, start.isoformat(), end.isoformat())
        
        if audio_data.size == 0:
            return None, 0

        # 2. Determine the original sample rate
        original_sr = get_sensor_sample_rate(db, collection)
        
        # 3. Determine the target sample rate
        final_sr = target_sr_config if target_sr_config else original_sr

        # 4. Resample if necessary
        if final_sr != original_sr:
            logging.debug(f"Resampling '{collection}' from {original_sr}Hz to {final_sr}Hz.")
            # AudioProcessor (resampy/librosa) expects float32. Convert int16 to float [-1.0, 1.0]
            if audio_data.dtype == np.int16:
                 # Divide by the maximum absolute value for 16-bit signed integer
                 audio_float = audio_data.astype(np.float32) / 32768.0
            else:
                 # Handle other types if necessary, assume normalized float if not int16
                 audio_float = audio_data.astype(np.float32)

            resampled_audio = audio_processor.resample_audio(audio_float, original_sr, final_sr)
            # The output of resampling is float32.
            return resampled_audio, final_sr
        
        # If no resampling needed, return original data (int16) and SR
        return audio_data, original_sr

    except Exception as e:
        logging.error(f"Failed to fetch or process audio for '{collection}' from {start} to {end}: {e}")
        return None, 0

def save_audio_clip(output_path: Path, audio_data: np.ndarray, sample_rate: int, format: str):
    """Saves a numpy audio array to a file."""
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Handle data types for saving.
        if audio_data.dtype == np.float32 or audio_data.dtype == np.float64:
             # If data is float (e.g., after resampling), ensure it's clipped before saving.
             # Soundfile handles the conversion to PCM formats correctly from float.
             audio_data = np.clip(audio_data, -1.0, 1.0)
        
        sf.write(str(output_path), audio_data, samplerate=sample_rate, format=format.upper())
    except Exception as e:
        logging.error(f"Failed to write audio file to {output_path}: {e}")
        raise

# --- Unified Export Engine Implementation ---

def run_export_job(config: ExportConfig):
    """The central engine that executes the export job based on the configuration."""
    output_base_dir = Path(config.output_config.base_directory)
    # Ensure the directory exists
    output_base_dir.mkdir(parents=True, exist_ok=True)

    run_id = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    setup_logging(output_base_dir, f"export_{config.export_job_name}_{run_id}.log")
    
    logging.info(f"--- Starting Unified Export Job: {config.export_job_name} (Type: {config.export_type}) ---")

    # 1. Initialize maps and database session
    sensor_to_group_name, group_name_to_object = create_group_maps(config.groups)
    try:
        db = get_db_session()
    except RuntimeError as e:
        logging.error(f"Failed to initialize database session: {e}")
        return

    # 2. Query Source Events
    source_events = query_source_events(db, config)
    if not source_events:
        logging.info("No events found matching the source configuration. Exiting.")
        db.close()
        return

    logging.info(f"Found {len(source_events)} source events (or aggregated convoys) to process.")

    # 3. Initialize Manifest Writers
    manifest_writers = {}
    try:
        manifest_writers = initialize_manifests(config, output_base_dir)
    except Exception:
        # Errors logged in initialize_manifests
        db.close()
        return

    # 4. Process Events
    total_clips_created = 0
    try:
        for event in source_events:
            clips_created = process_event(db, config, event, sensor_to_group_name, group_name_to_object, output_base_dir, manifest_writers)
            total_clips_created += clips_created
            # Commit periodically if managing large datasets, but for exports usually fine to commit at end or rely on autocommit/context manager if used.
            # db.commit()
            
    except Exception as e:
        logging.error(f"An unexpected error occurred during event processing: {e}", exc_info=True)
    finally:
        # 5. Finalize
        close_manifests(manifest_writers)
        logging.info(f"--- Export Job Complete. Total clips created: {total_clips_created} ---")
        db.close()

def query_source_events(db: Session, config: ExportConfig) -> List[Base]:
    """Queries the appropriate SQLAlchemy model based on the configuration."""
    SourceModel = TABLE_MODEL_MAP.get(config.source_config.database_table)
    if not SourceModel:
        logging.error(f"Invalid database table specified in config: {config.source_config.database_table}")
        return []
        
    # Check if the table actually exists in the database before querying
    if engine and not inspect(engine).has_table(config.source_config.database_table):
         logging.error(f"Source table '{config.source_config.database_table}' does not exist in the database.")
         return []

    query = db.query(SourceModel)

    # Apply filters dynamically
    filters = config.source_config.filters
    if filters:
        logging.info(f"Applying filters: {filters}")
        filter_clauses = []
        for key, value in filters.items():
            if not hasattr(SourceModel, key):
                logging.warning(f"Filter key '{key}' not found in model for table '{config.source_config.database_table}'. Skipping filter.")
                continue
            
            column = getattr(SourceModel, key)
            if value is None:
                filter_clauses.append(column.is_(None))
            elif isinstance(value, list):
                filter_clauses.append(column.in_(value))
            else:
                filter_clauses.append(column == value)
        
        if filter_clauses:
            query = query.filter(*filter_clauses)

    # Special handling for 'convoy' type: We need to aggregate event times.
    if config.export_type == "convoy":
        if SourceModel != Event:
             logging.error("Convoy export type requires 'events' table as source.")
             return []
        # This function handles the aggregation logic
        return aggregate_convoy_events(db, query)

    # Ensure start_timestamp exists before ordering (it should for all mapped models)
    if hasattr(SourceModel, 'start_timestamp'):
        return query.order_by(SourceModel.start_timestamp).all()
    
    # Should be unreachable due to TABLE_MODEL_MAP definitions
    logging.error(f"Source model for '{config.source_config.database_table}' lacks 'start_timestamp'. Cannot proceed.")
    return []

def aggregate_convoy_events(db: Session, base_query: Any) -> List[Event]:
    """Aggregates individual events belonging to the same convoy into a single encompassing event."""
    
    # We need to find the distinct convoy IDs present in the results of the base query (which includes filters).
    # Create a subquery from the base query to filter for non-null convoy_ids
    filtered_query = base_query.filter(Event.convoy_id.isnot(None))
    
    # Now, perform aggregation (MIN/MAX timestamp) grouped by convoy_id on the filtered query results.
    # We query from the filtered results (using from_self() or by redefining the query base)
    
    # Redefining the query structure for aggregation:
    aggregation_query = db.query(
        Event.convoy_id,
        func.min(Event.start_timestamp).label("start_timestamp"),
        func.max(Event.end_timestamp).label("end_timestamp")
    ).filter(Event.convoy_id.isnot(None))

    # Re-apply filters from the base query to the aggregation query if necessary
    # This part is tricky as filters might apply to individual events, not the aggregated convoy.
    # For simplicity here, we assume filters in the config are meant to select which convoys to include.
    # If complex filtering on event attributes is needed, the logic becomes more complex.
    
    # For now, we rely on the filters already applied in the config if they target 'convoy_id'.
    # If other filters were applied (e.g., status), they should have been applied before aggregation.
    
    # If the base_query already has filters applied, we should ideally use its results.
    # A more robust approach uses a subquery of the filtered events:
    
    # 1. Get IDs of events matching filters
    event_ids = [e.id for e in base_query.filter(Event.convoy_id.isnot(None)).all()]
    
    if not event_ids:
        return []

    # 2. Aggregate based on those specific event IDs
    aggregation_query = db.query(
        Event.convoy_id,
        func.min(Event.start_timestamp).label("start_timestamp"),
        func.max(Event.end_timestamp).label("end_timestamp")
    ).filter(Event.id.in_(event_ids)).group_by(Event.convoy_id)

    results = aggregation_query.all()
    
    aggregated_events = []
    for convoy_id, start_ts, end_ts in results:
        if start_ts and end_ts:
            # Create a synthetic Event object representing the whole convoy duration
            # We treat the convoy itself as the "vehicle type" for organizational purposes
            convoy_event = Event(
                id=f"CONVOY_{convoy_id}",
                start_timestamp=start_ts,
                end_timestamp=end_ts,
                vehicle_type=f"Convoy_{convoy_id}",
                vehicle_action="convoy_passage",
                convoy_id=convoy_id
            )
            aggregated_events.append(convoy_event)
    
    return aggregated_events


def initialize_manifests(config: ExportConfig, base_dir: Path) -> Dict[str, csv.DictWriter]:
    """Opens file handles and initializes CSV writers for the manifests."""
    if not config.truth_file_config.enabled:
        return {}

    writers = {}
    fieldnames = [
        'clip_id', 'source_event_id', 'group_name', 'sensor_name', 
        'event_start_utc', 'event_end_utc', 'clip_start_utc', 'clip_end_utc', 
        'duration_s', 'file_path_relative', 'vehicle_type', 'action', 'direction', 'location',
        'sample_rate', 'export_job_name'
    ]

    def create_writer(path: Path):
        try:
            # Open in write mode ('w') to overwrite previous exports for the same job definition
            f = open(path, 'w', newline='')
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            # Store the file handle on the writer object itself for easy closing later
            writer._file_handle = f
            return writer
        except IOError as e:
            logging.error(f"Could not open manifest file {path}: {e}")
            raise

    if config.truth_file_config.mode == "single":
        manifest_path = base_dir / config.truth_file_config.filename
        writers["_master"] = create_writer(manifest_path)
    
    elif config.truth_file_config.mode == "per_group":
        # Create a dedicated subfolder for manifests to keep the root clean
        manifest_dir = base_dir / "manifests_by_location"
        manifest_dir.mkdir(parents=True, exist_ok=True)

        for group in config.groups:
            # Filename format: JOBNAME_GROUPNAME_manifest.csv
            job_name_sanitized = sanitize_for_path(config.export_job_name)
            group_name_sanitized = sanitize_for_path(group.name)
            filename = f"{job_name_sanitized}_{group_name_sanitized}_{config.truth_file_config.filename}"
            manifest_path = manifest_dir / filename
            
            try:
                writers[group.name] = create_writer(manifest_path)
            except IOError:
                # If creating one fails, clean up any already opened ones before raising
                close_manifests(writers)
                raise
    
    return writers

def close_manifests(writers: Dict[str, csv.DictWriter]):
    """Closes all open file handles associated with the manifest writers."""
    for writer in writers.values():
        # Check for the custom attribute where we stored the handle
        if hasattr(writer, '_file_handle') and writer._file_handle and not writer._file_handle.closed:
            try:
                writer._file_handle.close()
            except Exception as e:
                logging.warning(f"Error closing manifest file handle: {e}")

def process_event(db: Session, config: ExportConfig, event: Base, sensor_to_group_name: Dict[str, str], group_name_to_object: Dict[str, SensorGroup], base_dir: Path, writers: Dict[str, csv.DictWriter]) -> int:
    """Processes a single source event, propagating it across relevant sensor groups."""
    
    # Ensure timestamps are timezone-aware (assuming DB stores them as naive UTC if tzinfo is missing)
    event_start = event.start_timestamp
    event_end = event.end_timestamp

    # Handle potential non-datetime objects if aggregation returns different types
    if not isinstance(event_start, datetime) or not isinstance(event_end, datetime):
        logging.error(f"Event {event.id} timestamps are not datetime objects. Skipping.")
        return 0

    if event_start.tzinfo is None:
        event_start = event_start.replace(tzinfo=timezone.utc)
    if event_end.tzinfo is None:
        event_end = event_end.replace(tzinfo=timezone.utc)

    # Determine which groups are relevant for this event.
    relevant_groups = determine_relevant_groups(config, event, sensor_to_group_name, group_name_to_object, event_start, event_end)
    
    if not relevant_groups:
        # Logging handled inside determine_relevant_groups
        return 0

    clips_created = 0
    for group in relevant_groups:
        logging.info(f"Processing Event ID {event.id[:8]} for Group: {group.name} | Time: {event_start.isoformat()}")
        
        # For each relevant group, iterate over all sensors in that group
        for target_sensor in group.collections:
            # Determine the time windows (clips) to export for this specific sensor
            if config.processing_config.windowing:
                windows = generate_windows_with_final_capture(event_start, event_end, config.processing_config.windowing)
                if not windows:
                     logging.debug(f"  Event duration ({(event_end-event_start).total_seconds():.2f}s) too short for window size. Skipping.")
                     # Break the inner loop (windows) but continue to the next sensor
                     continue
            else:
                # Export the full duration as a single window
                windows = [(event_start, event_end)]
            
            for clip_start, clip_end in windows:
                # Process and save the clip
                success = export_clip(db, config, event, group, target_sensor, clip_start, clip_end, base_dir, writers)
                if success:
                    clips_created += 1
    
    return clips_created

def determine_relevant_groups(config: ExportConfig, event: Base, sensor_to_group_name: Dict[str, str], group_name_to_object: Dict[str, SensorGroup], start: datetime, end: datetime) -> List[SensorGroup]:
    """Identifies which sensor groups should be included in the export for a given event. This implements location awareness."""
    
    # Method 1: Explicit association (common for refined_annotations or annotations)
    # Try to find the sensor name directly on the event object.
    primary_sensor = None
    if hasattr(event, 'source_collection') and event.source_collection:
        primary_sensor = event.source_collection
    elif hasattr(event, 'sensor') and event.sensor:
        primary_sensor = event.sensor

    if primary_sensor:
        group_name = sensor_to_group_name.get(primary_sensor)
        if group_name and group_name in group_name_to_object:
            # If the event is explicitly linked to a sensor in a known group, use only that group.
            return [group_name_to_object[group_name]]
        else:
            # Gotcha: Event sensor not in any configured group
            logging.info(f"Event ID {event.id} sensor '{primary_sensor}' is not in any configured export group. Skipping.")
            return []

    # Method 2: Implicit association (common for generic 'events' table, e.g., single_vehicle/convoy)
    # If no primary sensor is listed on the event, we must check which groups have data during the event time.
    
    if config.export_type in ["single_vehicle", "convoy", "generic"]:
        logging.debug(f"Event ID {event.id} has no explicit sensor. Checking data availability across groups.")
        relevant = []
        if not questdb_client:
             logging.error("QuestDB client not available. Cannot check data existence.")
             return []
             
        for group in config.groups:
            # A robust check ensures the reference sensor for the group has data during the event time.
            if questdb_client.check_data_exists(group.reference_sensor, start.isoformat(), end.isoformat()):
                relevant.append(group)
            else:
                logging.debug(f"Group '{group.name}' excluded for event {event.id}: reference sensor '{group.reference_sensor}' lacks data in the time range.")
        return relevant
    
    # If model_training type and no explicit sensor, we cannot determine the group reliably.
    logging.info(f"Event ID {event.id} (Type: {config.export_type}) lacks sensor identifier and cannot be associated with a group. Skipping.")
    return []

def export_clip(db: Session, config: ExportConfig, event: Base, group: SensorGroup, target_sensor: str, clip_start: datetime, clip_end: datetime, base_dir: Path, writers: Dict[str, csv.DictWriter]) -> bool:
    """Handles the fetching, processing, saving, and manifest writing for a single audio clip."""
    
    # 1. Fetch and Process Audio (Handles sample rate determination and resampling)
    audio_data, final_sr = fetch_and_process_audio(db, target_sensor, clip_start, clip_end, config.processing_config.target_sample_rate)
    
    if audio_data is None or audio_data.size == 0:
        # Logged in fetch_and_process_audio, just return failure
        return False

    # 2. Generate Output Path and Clip ID
    event_id_prefix = sanitize_for_path(event.id[:8])
    # Format timestamp for filename: YYYYMMDDTHHMMSSmmm (ISO-like but filename safe)
    clip_start_ts_str = clip_start.strftime('%Y%m%dT%H%M%S%f')[:-3]
    clip_id = f"{event_id_prefix}_{target_sensor}_{clip_start_ts_str}"

    # Gather and sanitize template variables
    # We use getattr to safely access attributes that might differ between source tables (Event vs RefinedAnnotation)
    template_vars = {
        "group_name": sanitize_for_path(group.name),
        "vehicle_type": sanitize_for_path(getattr(event, 'vehicle_type', None)),
        "event_id": sanitize_for_path(event.id),
        "event_id_prefix": event_id_prefix,
        "convoy_id": sanitize_for_path(getattr(event, 'convoy_id', None)),
        "sensor_name": sanitize_for_path(target_sensor),
        "clip_start_ts": clip_start_ts_str,
        "clip_id": clip_id, 
        "format": config.output_config.format.lower(),
        # Handle variations in action naming (e.g., 'action' vs 'vehicle_action')
        "action": sanitize_for_path(getattr(event, 'action', getattr(event, 'vehicle_action', None))),
        "location": sanitize_for_path(getattr(event, 'location', None)),
        "direction": sanitize_for_path(getattr(event, 'direction', None)),
    }

    try:
        relative_path_str = config.output_config.file_path_template.format(**template_vars)
        output_path = base_dir / relative_path_str
    except KeyError as e:
        logging.error(f"Invalid variable in file_path_template: {e}. Check configuration template variables. Skipping clip.")
        return False
    except Exception as e:
        logging.error(f"Error formatting file path template: {e}. Skipping clip.")
        return False

    # 3. Save Audio Clip
    try:
        save_audio_clip(output_path, audio_data, final_sr, config.output_config.format)
    except Exception:
        # Error logged in save_audio_clip
        return False

    # 4. Write Manifest Entry
    if config.truth_file_config.enabled:
        # Determine the correct writer
        writer = None
        if config.truth_file_config.mode == "single":
            writer = writers.get("_master")
        elif config.truth_file_config.mode == "per_group":
            writer = writers.get(group.name)
        
        if writer:
            try:
                # Ensure timestamps are correctly formatted ISO strings for the manifest
                # Handle potential non-datetime objects if source data is inconsistent
                event_start_iso = event.start_timestamp.isoformat() if isinstance(event.start_timestamp, datetime) else str(event.start_timestamp)
                event_end_iso = event.end_timestamp.isoformat() if isinstance(event.end_timestamp, datetime) else str(event.end_timestamp)

                writer.writerow({
                    'clip_id': clip_id,
                    'source_event_id': event.id,
                    'group_name': group.name,
                    'sensor_name': target_sensor,
                    'event_start_utc': event_start_iso,
                    'event_end_utc': event_end_iso,
                    'clip_start_utc': clip_start.isoformat(),
                    'clip_end_utc': clip_end.isoformat(),
                    'duration_s': (clip_end - clip_start).total_seconds(),
                    'file_path_relative': relative_path_str,
                    'vehicle_type': template_vars['vehicle_type'],
                    'action': template_vars['action'],
                    'direction': template_vars['direction'],
                    'location': template_vars['location'],
                    'sample_rate': final_sr,
                    'export_job_name': config.export_job_name
                })
            except Exception as e:
                logging.error(f"Failed to write manifest entry for clip {clip_id}: {e}")
                # Continue execution even if manifest writing fails

    return True


# --- CLI Interface ---

# Unified CLI entry point
@click.group()
def cli():
    """A unified CLI tool for exporting annotated audio data."""
    # Ensure basic logging is set up if not already configured
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')

# Replace the old commands (model-training, single-vehicle, convoy) with a single 'run' command.
@cli.command(name="run")
@click.argument('config_path', type=click.Path(exists=True, dir_okay=False))
@click.option('--output-dir', type=click.Path(file_okay=False), default=None, help='Override the base_directory specified in the config.')
def run_export_cli(config_path: str, output_dir: Optional[str]):
    """
    Executes an export job based on a unified JSON configuration file (CONFIG_PATH).
    """
    
    try:
        config = ExportConfig.from_json(config_path)
    except Exception as e:
        # Use print here as logging might not be fully set up until run_export_job
        print(f"ERROR: Failed to load or validate configuration file '{config_path}': {e}")
        exit(1)

    if output_dir:
        # Override the output directory if provided via CLI
        config.output_config.base_directory = Path(output_dir)

    try:
        run_export_job(config)
    except Exception as e:
        # Logging is active inside run_export_job
        logging.error(f"Export job failed with critical error: {e}", exc_info=True)
        exit(1)

if __name__ == '__main__':
    # Ensure compatibility with multiprocessing if the underlying libraries use it
    from multiprocessing import freeze_support
    freeze_support()
    cli()