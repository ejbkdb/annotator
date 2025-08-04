# examples/complete_workflow.py
import os
import shutil
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import numpy as np

# Import our system components
from backend.database_migrations import apply_migrations, PipelineConfiguration, Annotation
from backend.pipeline_config import PipelineConfig
from backend.smart_alignment import align_multi_sensor_event
from backend.incremental_processor import run_pipeline_incrementally
from backend.ml_export_advanced import export_data
from backend.quality_checks import run_quality_checks

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Workflow Configuration ---
WORK_DIR = Path("./workflow_example_run/")
DB_PATH = WORK_DIR / "test_system.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"
EXPORT_DIR = WORK_DIR / "ml_ready"
SAMPLE_RATE = 16000

def setup_environment():
    """Clean up previous runs and set up a fresh environment."""
    logging.info("--- 0. Setting up environment ---")
    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)
    WORK_DIR.mkdir(parents=True)
    
    # Set environment variable for other modules to use
    os.environ["ANNOTATOR_DB_URL"] = DATABASE_URL
    apply_migrations()
    logging.info(f"Environment ready at: {WORK_DIR.resolve()}")

def ingest_and_align():
    """Simulate ingesting data for an event and finding alignment."""
    logging.info("--- 1. Simulating Data Ingestion & Alignment ---")
    # Simulate a single event captured by three sensors with known offsets
    base_signal = np.sin(np.linspace(0, 10 * np.pi, SAMPLE_RATE * 2)) # A 2-second sine wave
    event_audio = {
        "sensor_ref": np.pad(base_signal, (SAMPLE_RATE // 2, SAMPLE_RATE // 2)),
        "sensor_A":   np.pad(base_signal, (SAMPLE_RATE // 2 + 200, SAMPLE_RATE // 2 - 200)), # 200 samples late
        "sensor_B":   np.pad(base_signal, (SAMPLE_RATE // 2 - 350, SAMPLE_RATE // 2 + 350)), # 350 samples early
    }
    
    offsets_samples, confidences = align_multi_sensor_event(event_audio, "sensor_ref", SAMPLE_RATE)
    offsets_ms = {k: v / SAMPLE_RATE * 1000 for k, v in offsets_samples.items()}

    logging.info(f"Discovered Offsets (ms): {offsets_ms}")
    logging.info(f"Alignment Confidences: {confidences}")
    return offsets_ms

def create_and_run_pipeline(offsets_ms: dict):
    """Create a pipeline config, save it, and run initial processing."""
    logging.info("--- 2. Creating and Running Initial Pipeline ---")
    # Define the pipeline configuration
    config_data = {
      "pipeline_id": "prod_pipeline_v1",
      "input": {
        "collections": ["sensor_ref", "sensor_A"], # Initially, only process two sensors
        "time_range": {"start": "2025-08-01T00:00:00Z", "end": None}
      },
      "alignment": {
        "reference_sensor": "sensor_ref",
        "offsets": {k: int(v) for k, v in offsets_ms.items()}
      },
      "processing": { "window_size_seconds": 1.0, "overlap_seconds": 0.5, "target_sample_rate": SAMPLE_RATE },
      "output": { "base_directory": str(EXPORT_DIR), "structure": "{action}/{sensor}/", "format": "flac" }
    }
    config = PipelineConfig(**config_data)
    config_path = WORK_DIR / "pipeline_prod.json"
    config.to_json(config_path)
    
    # Setup DB connection
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    db = Session()
    
    # Save config to DB
    db.add(PipelineConfiguration(pipeline_id=config.pipeline_id, config_json=config.model_dump()))
    
    # Add a dummy annotation to the DB for the processor/exporter to find
    now = datetime.now()
    db.add(Annotation(id=str(uuid.uuid4()), sensor="sensor_A", start_timestamp=now, end_timestamp=now + timedelta(seconds=10), action="driveby"))
    db.commit()

    # Run initial processing
    run_pipeline_incrementally(config, db)
    db.close()
    return config

def add_sensor_and_reprocess(config: PipelineConfig):
    """Simulate adding a new sensor to the pipeline and running an incremental update."""
    logging.info("--- 3. Adding New Sensor and Rerunning ---")
    # Update the config to include the new sensor
    config.input.collections.append("sensor_B")
    logging.info(f"Updated collections: {config.input.collections}")

    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    db = Session()

    # Simulate adding an annotation for the new sensor
    now = datetime.now()
    db.add(Annotation(id=str(uuid.uuid4()), sensor="sensor_B", start_timestamp=now, end_timestamp=now + timedelta(seconds=5), action="rev"))
    db.commit()
    
    # The incremental processor should find the new sensor and process its data
    run_pipeline_incrementally(config, db)
    db.close()

def export_and_validate(config: PipelineConfig):
    """Export the processed data and run quality checks."""
    logging.info("--- 4. Exporting Data and Running QA ---")
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    db = Session()

    export_data(config, db, incremental=False) # Run a full export for the example
    
    manifest_path = EXPORT_DIR / "manifest.csv"
    report = run_quality_checks(str(EXPORT_DIR), str(manifest_path))
    
    logging.info("QA Report Summary:")
    logging.info(json.dumps(report, indent=2))
    db.close()

if __name__ == "__main__":
    setup_environment()
    discovered_offsets = ingest_and_align()
    pipeline_config = create_and_run_pipeline(discovered_offsets)
    add_sensor_and_reprocess(pipeline_config)
    export_and_validate(pipeline_config)
    logging.info("--- ✅ Complete workflow finished successfully! ---")