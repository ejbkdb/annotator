# examples/complete_workflow.py
import os
import shutil
import json
import logging
import uuid # Needed for generating annotation IDs
from pathlib import Path
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import numpy as np
# IMPLEMENTATION: Added for real audio file generation
import soundfile as sf
from scipy import signal 

# Import our system components
# IMPLEMENTATION: Use the new SQLAlchemy models location
from backend.models_sqlalchemy import apply_migrations, PipelineConfiguration, Annotation, Base, SensorMetadata, ProcessingResult
from backend.pipeline_config import PipelineConfig
# Smart alignment is still useful, keeping it.
from backend.smart_alignment import align_multi_sensor_event
from backend.incremental_processor import run_pipeline_incrementally
from backend.ml_export_advanced import export_data
from backend.quality_checks import run_quality_checks
# IMPLEMENTATION: Import the real ingestion utility and client
from backend.ingestion_utils import run_bulk_ingestion
from backend import questdb_client

# Configure logging
if not logging.getLogger().hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Workflow Configuration ---
WORK_DIR = Path("./workflow_example_run/")
DB_PATH = WORK_DIR / "test_system.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"
EXPORT_DIR = WORK_DIR / "ml_ready"
INGEST_DIR = WORK_DIR / "ingest_data"
SAMPLE_RATE = 48000 # Use a realistic sample rate

def setup_environment():
    """Clean up previous runs and set up a fresh environment."""
    logging.info("--- 0. Setting up environment ---")
    # IMPLEMENTATION: Real cleanup of the working directory
    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)
        
    WORK_DIR.mkdir(parents=True)
    INGEST_DIR.mkdir(exist_ok=True)
    
    # Set environment variable for other modules to use
    os.environ["ANNOTATOR_DB_URL"] = DATABASE_URL
    
    # Initialize the SQLite database
    apply_migrations()
    
    # IMPLEMENTATION: Clean up QuestDB tables (Requires connection)
    # This ensures the example is repeatable.
    try:
        conn = questdb_client._get_pg_connection()
        cur = conn.cursor()
        # Clean up tables used in this example
        cur.execute("DROP TABLE IF EXISTS sensor_ref;")
        cur.execute("DROP TABLE IF EXISTS sensor_a;")
        cur.execute("DROP TABLE IF EXISTS sensor_b;")
        conn.commit()
        conn.close()
        logging.info("QuestDB tables cleared (sensor_ref, sensor_a, sensor_b).")
    except Exception as e:
        logging.warning(f"Could not connect to or clean QuestDB. Ensure it is running (docker-compose up). Error: {e}")

    logging.info(f"Environment ready at: {WORK_DIR.resolve()}")

def generate_and_ingest_data():
    """Generate synthetic WAV files and ingest them into QuestDB."""
    logging.info("--- 1. Generating and Ingesting Synthetic Data ---")
    
    # Define sensors and their simulated time offsets (in samples)
    sensors = {
        "sensor_ref": 0,
        "sensor_A": 500,  # Late (500 samples)
        "sensor_B": -800, # Early (800 samples)
    }
    
    # Define the event time (using current time for realism)
    event_time = datetime.now(timezone.utc).replace(microsecond=0)
    
    # Generate a base signal
    duration_s = 10
    t = np.linspace(0., duration_s, int(SAMPLE_RATE * duration_s))
    # IMPLEMENTATION: Generate a recognizable synthetic signal (chirp) and convert to int16 for WAV
    base_signal = (signal.chirp(t, f0=100, f1=5000, t1=duration_s, method='logarithmic') * 30000).astype(np.int16)

    ingested_collections = []
    
    for sensor, offset in sensors.items():
        logging.info(f"Generating data for {sensor} with offset {offset} samples.")
        
        # Apply offset to the signal data
        if offset > 0:
            # Late signal: pad start with zeros, truncate end
            signal_data = np.pad(base_signal, (offset, 0), mode='constant', constant_values=0)[:len(base_signal)]
        elif offset < 0:
            # Early signal: truncate start, pad end with zeros
            signal_data = np.pad(base_signal[-offset:], (0, -offset), mode='constant', constant_values=0)
        else:
            signal_data = base_signal
            
        # Filename timestamp must reflect the start time of the audio file content for ingestion parsing
        # The actual start time of the file content shifts based on the offset
        file_start_time = event_time + timedelta(seconds=offset/SAMPLE_RATE)
        
        # Format required by the ingestion parser (YYYYMMDD_HHMMSS)
        filename = f"AUDIO_{file_start_time.strftime('%Y%m%d_%H%M%S')}.WAV"
        sensor_dir = INGEST_DIR / sensor
        sensor_dir.mkdir(parents=True, exist_ok=True)
        filepath = sensor_dir / filename
        
        # IMPLEMENTATION: Write the actual WAV file to disk
        sf.write(str(filepath), signal_data, SAMPLE_RATE)
        
        # IMPLEMENTATION: Ingest the data using the real utility
        try:
            logging.info(f"Ingesting from {sensor_dir} into collection {sensor}...")
            # The utility function handles the directory ingestion
            run_bulk_ingestion(str(sensor_dir), sensor)
            ingested_collections.append(sensor)
        except Exception as e:
            logging.error(f"Failed to ingest data for {sensor}: {e}")

    # Update SensorMetadata in SQLite
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        for sensor in ingested_collections:
             # IMPLEMENTATION: Real DB operation (UPSERT)
             db.merge(SensorMetadata(collection_name=sensor, sample_rate=SAMPLE_RATE))
        db.commit()
    finally:
        db.close()

    return ingested_collections, event_time

def create_annotations(event_time: datetime, collections: list):
    """Create initial annotations for the ingested event."""
    logging.info("--- 2. Creating Initial Annotations ---")
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    db = Session()
    
    # Create annotations slightly offset from the start, covering the main event
    start_time = event_time + timedelta(seconds=1)
    end_time = event_time + timedelta(seconds=9)
    
    annotations = []
    for sensor in collections:
        # IMPLEMENTATION: Create real annotation objects
        annotations.append(
            Annotation(
                id=str(uuid.uuid4()), sensor=sensor, 
                start_timestamp=start_time, end_timestamp=end_time, 
                action="driveby", vehicle_type="example_vehicle", location="test_site",
                status="refined" # Set status so it's picked up by the exporter
            )
        )
    
    # IMPLEMENTATION: Real DB insertion
    db.add_all(annotations)
    db.commit()
    logging.info(f"Created {len(annotations)} annotations.")
    db.close()

def create_and_run_pipeline(collections: list):
    """Create a pipeline config, save it, and run processing."""
    logging.info("--- 3. Creating and Running Pipeline ---")
    
    # Define the pipeline configuration
    config_data = {
        "pipeline_id": "example_pipeline_v1",
        "input": {
            "collections": collections,
            # Define a time range encompassing the event (Now() +/- 5 mins)
            # This ensures the processor looks at the time range where we ingested data.
            "time_range": {
                "start": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(), 
                "end": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
            }
        },
        "alignment": {
            "reference_sensor": "sensor_ref",
            "offsets": {} # In this example, we rely on the ingestion time alignment.
        },
        # Process in 2s windows with 1s overlap
        "processing": { "window_size_seconds": 2.0, "overlap_seconds": 1.0, "target_sample_rate": SAMPLE_RATE },
        # Ensure the path is absolute for the config validation
        "output": { "base_directory": str(EXPORT_DIR.resolve()), "structure": "{vehicle_type}/{action}/{sensor}/", "format": "flac" }
    }
    config = PipelineConfig(**config_data)
    config_path = WORK_DIR / "pipeline_config.json"
    config.to_json(config_path)
    
    # Setup DB connection
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    db = Session()
    
    # Save config to DB (REAL IMPLEMENTATION - UPSERT)
    db.merge(PipelineConfiguration(pipeline_id=config.pipeline_id, config_json=config.model_dump()))
    db.commit()

    # Run processing (REAL IMPLEMENTATION)
    logging.info("Running incremental processing (feature extraction)...")
    run_pipeline_incrementally(config, db)
    
    # Verify results were written (REAL IMPLEMENTATION)
    result_count = db.query(ProcessingResult).count()
    logging.info(f"Processing complete. Generated {result_count} processing results (features).")
    
    db.close()
    return config

def export_and_validate(config: PipelineConfig):
    """Export the processed data and run quality checks."""
    logging.info("--- 4. Exporting Data and Running QA ---")
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    db = Session()

    # Run export (REAL IMPLEMENTATION)
    export_data(config, db, incremental=False) # Run a full export for the example
    
    manifest_path = EXPORT_DIR / "manifest.csv"
    
    # IMPLEMENTATION: Check if export actually succeeded
    if not manifest_path.exists():
        logging.error("Export failed: Manifest file not created.")
        db.close()
        return

    # Run quality checks (REAL IMPLEMENTATION)
    # Note: quality_checks.py was already implemented, just calling it.
    report = run_quality_checks(str(EXPORT_DIR), str(manifest_path))
    
    logging.info("QA Report Summary:")
    logging.info(f"Total Clips: {report['summary']['total_clips']}")
    logging.info(f"Failed Clips: {report['summary']['failed_clips']}")
    if report['duration_failures']:
        logging.warning(f"Duration Failures: {len(report['duration_failures'])}")
    if report['silence_corruption_failures']:
         logging.warning(f"Silence/Corruption Failures: {len(report['silence_corruption_failures'])}")

    db.close()

if __name__ == "__main__":
    # Ensure compatibility with multiprocessing when run as a script
    from multiprocessing import freeze_support
    freeze_support()
    
    setup_environment()
    try:
        # IMPLEMENTATION: Replaced simulated steps with real generation and ingestion
        collections, event_time = generate_and_ingest_data()
        if not collections:
            logging.error("Data ingestion failed or returned no collections. Aborting workflow. Ensure QuestDB is running and accessible.")
            exit(1)
            
        create_annotations(event_time, collections)
        pipeline_config = create_and_run_pipeline(collections)
        export_and_validate(pipeline_config)
        logging.info("--- ✅ Complete workflow finished successfully! ---")
        logging.info(f"Check results in: {WORK_DIR.resolve()}")
        
    except Exception as e:
        logging.error(f"Workflow failed: {e}", exc_info=True)

