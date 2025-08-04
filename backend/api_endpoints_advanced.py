# backend/api_endpoints_advanced.py
import os
import uuid
import logging
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pathlib import Path
from typing import Optional

# Import necessary components
from .pipeline_config import PipelineConfig
# IMPLEMENTATION: Import SQLAlchemy models from the new location
from .models_sqlalchemy import Base, PipelineConfiguration, ProcessingHistory, SensorMetadata, Annotation, apply_migrations
from .incremental_processor import run_pipeline_incrementally
# IMPLEMENTATION: Import the real ingestion utility
from .ingestion_utils import run_bulk_ingestion
from .ml_export_advanced import export_data

# --- Configuration ---
DATABASE_URL = os.environ.get("ANNOTATOR_DB_URL", "sqlite:///./annotation_system.db")
# Configure logging
if not logging.getLogger().hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- FastAPI App & DB Setup ---
app = FastAPI(title="Production Audio Annotation API (Advanced)")

# Determine connection arguments based on DB type
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Ensure tables are created on startup by running migrations
@app.on_event("startup")
def startup_event():
    apply_migrations()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- API Endpoints ---

@app.post("/api/pipeline/create", status_code=status.HTTP_201_CREATED)
def create_pipeline(config: PipelineConfig, db: Session = Depends(get_db)):
    """Creates or updates a pipeline configuration in the database."""
    # IMPLEMENTATION: Real database transaction with error handling
    try:
        existing_pipeline = db.query(PipelineConfiguration).filter_by(pipeline_id=config.pipeline_id).first()
        
        if existing_pipeline:
            logging.info(f"Updating existing pipeline: {config.pipeline_id}")
            existing_pipeline.config_json = config.model_dump()
            existing_pipeline.description = config.pipeline_id
        else:
            logging.info(f"Creating new pipeline: {config.pipeline_id}")
            new_pipeline = PipelineConfiguration(
                pipeline_id=config.pipeline_id,
                config_json=config.model_dump(),
                description=config.pipeline_id
            )
            db.add(new_pipeline)
            
        db.commit()
        return {"message": f"Pipeline '{config.pipeline_id}' saved successfully."}
    except Exception as e:
        db.rollback()
        logging.error(f"Failed to create/update pipeline: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Database operation failed.")

# IMPLEMENTATION: Helper function for background processing task (must be defined outside the endpoint)
def background_processing_task(config: PipelineConfig):
    # Create a new, independent database session specifically for the background task
    db_session = SessionLocal()
    try:
        logging.info(f"Starting background processing for pipeline {config.pipeline_id}")
        # IMPLEMENTATION: Call the actual processor
        run_pipeline_incrementally(config, db_session)
        logging.info(f"Background processing finished for pipeline {config.pipeline_id}")
    except Exception as e:
        logging.error(f"Background processing failed for pipeline {config.pipeline_id}: {e}", exc_info=True)
        db_session.rollback()
    finally:
        db_session.close()

@app.post("/api/pipeline/{pipeline_id}/run", status_code=status.HTTP_202_ACCEPTED)
def run_pipeline(pipeline_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Triggers an incremental processing run for a pipeline in the background."""
    # IMPLEMENTATION: Real DB lookup
    p_config_db = db.query(PipelineConfiguration).filter_by(pipeline_id=pipeline_id).first()
    if not p_config_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Pipeline '{pipeline_id}' not found.")
        
    config = PipelineConfig(**p_config_db.config_json)
    
    # IMPLEMENTATION: Add the actual processing task to the background queue
    background_tasks.add_task(background_processing_task, config)
    
    return {"message": f"Pipeline run for '{pipeline_id}' has been initiated."}

@app.get("/api/pipeline/{pipeline_id}/status")
def get_pipeline_status(pipeline_id: str, db: Session = Depends(get_db)):
    """Retrieves the processing history and status for a pipeline."""
    # IMPLEMENTATION: Real database query fetching detailed history
    history = db.query(ProcessingHistory).filter_by(pipeline_id=pipeline_id).order_by(ProcessingHistory.run_timestamp.desc()).all()
    
    if not history:
        return {"pipeline_id": pipeline_id, "status": "No history found.", "sensors": {}}
        
    # Aggregate the latest status for each sensor
    status_by_sensor = {}
    for entry in history:
        # We iterate descending by time, so the first entry for a sensor is the latest.
        if entry.sensor_id not in status_by_sensor:
             status_by_sensor[entry.sensor_id] = {
                 "last_processed_end_utc": entry.processed_end_utc.isoformat(),
                 "last_run_utc": entry.run_timestamp.isoformat(),
                 "last_status": entry.status,
                 "details": entry.details
             }

    return {
        "pipeline_id": pipeline_id,
        "last_run_utc": history[0].run_timestamp.isoformat(),
        "sensors": status_by_sensor
    }

# IMPLEMENTATION: Helper function for the background ingestion and processing task
def background_ingestion_and_processing(path: str, collection: str):
    logging.info(f"Starting background ingestion task for '{collection}' from '{path}'.")
    
    # 1. Run Ingestion (REAL IMPLEMENTATION)
    try:
        total_points, successful_files = run_bulk_ingestion(path, collection)
        if successful_files == 0:
            logging.error(f"Ingestion failed or no files processed for '{collection}'.")
            return
        logging.info(f"Ingestion complete for '{collection}'. Points: {total_points}. Files: {successful_files}.")
    except Exception as e:
        logging.error(f"Ingestion process failed for '{collection}': {e}", exc_info=True)
        return

    # 2. Update Metadata and Trigger Pipelines
    scoped_db = SessionLocal()
    try:
        # Update metadata (REAL IMPLEMENTATION)
        # Use merge for UPSERT functionality
        sensor_meta = SensorMetadata(collection_name=collection, notes=f"Ingested from path: {path}")
        scoped_db.merge(sensor_meta)
        scoped_db.commit()
        
        # Find and run relevant pipelines (REAL IMPLEMENTATION)
        pipelines = scoped_db.query(PipelineConfiguration).all()
        for p_config_db in pipelines:
            config_dict = p_config_db.config_json
            if collection in config_dict.get('input', {}).get('collections', []):
                logging.info(f"Triggering pipeline '{p_config_db.pipeline_id}' for new collection '{collection}'.")
                try:
                    config = PipelineConfig(**config_dict)
                    # Run the pipeline synchronously within this background task
                    run_pipeline_incrementally(config, scoped_db)
                except Exception as e:
                    logging.error(f"Pipeline execution failed for {p_config_db.pipeline_id}: {e}", exc_info=True)
                    scoped_db.rollback()
                    
    except Exception as e:
        logging.error(f"Error during metadata update or pipeline triggering: {e}", exc_info=True)
        scoped_db.rollback()
    finally:
        scoped_db.close()

@app.post("/api/data/add-and-process", status_code=status.HTTP_202_ACCEPTED)
async def add_data_and_process(
    path: str = Query(..., description="Server-side path to the data directory"), 
    collection: str = Query(..., description="Name of the collection/sensor"),
    background_tasks: BackgroundTasks
):
    """
    Ingests new data from a specified path and triggers relevant pipelines in the background.
    """
    # IMPLEMENTATION: Validate input path exists on the server (Security measure)
    if not os.path.isdir(path):
         raise HTTPException(status_code=400, detail=f"Directory not found on server: {path}")

    # IMPLEMENTATION: The ingestion and subsequent processing are run as a background task
    background_tasks.add_task(background_ingestion_and_processing, path, collection)
    
    return {"message": f"Ingestion for '{collection}' from '{path}' initiated. Processing tasks started in background."}

# IMPLEMENTATION: Helper for background export
def background_export_task(config: PipelineConfig, incremental: bool):
    db_session = SessionLocal()
    try:
        logging.info(f"Starting background export task for {config.pipeline_id}. Incremental: {incremental}.")
        # IMPLEMENTATION: Call the real export logic
        export_data(config, db_session, incremental)
        logging.info(f"Export task finished for {config.pipeline_id}.")
    except Exception as e:
        logging.error(f"Background export failed: {e}", exc_info=True)
        db_session.rollback()
    finally:
        db_session.close()

@app.post("/api/export/{pipeline_id}", status_code=status.HTTP_202_ACCEPTED)
def trigger_export(
    pipeline_id: str, 
    background_tasks: BackgroundTasks, 
    incremental: bool = Query(True, description="Run incremental export (only new data) or full export."),
    db: Session = Depends(get_db)
):
    """Triggers an export job for the specified pipeline."""
    # IMPLEMENTATION: Real DB lookup
    p_config_db = db.query(PipelineConfiguration).filter_by(pipeline_id=pipeline_id).first()
    if not p_config_db:
        raise HTTPException(status_code=404, detail=f"Pipeline '{pipeline_id}' not found.")
        
    config = PipelineConfig(**p_config_db.config_json)

    # IMPLEMENTATION: Add real task to background queue
    background_tasks.add_task(background_export_task, config, incremental)
    return {"message": f"Export job for pipeline '{pipeline_id}' initiated."}


@app.get("/api/export/manifest/{pipeline_id}")
def get_export_manifest(pipeline_id: str, db: Session = Depends(get_db)):
    """Retrieves the export manifest file for a specific pipeline."""
    
    # IMPLEMENTATION: Real lookup of config to find the path
    p_config_db = db.query(PipelineConfiguration).filter_by(pipeline_id=pipeline_id).first()
    if not p_config_db:
        raise HTTPException(status_code=404, detail=f"Pipeline configuration '{pipeline_id}' not found.")

    try:
        config = PipelineConfig(**p_config_db.config_json)
        base_dir = Path(config.output.base_directory)
        manifest_path = base_dir / "manifest.csv"
    except Exception as e:
        # Handle errors if config is invalid (e.g. missing output directory)
        raise HTTPException(status_code=500, detail=f"Error parsing pipeline configuration: {e}")

    # IMPLEMENTATION: Check if the actual file exists on the filesystem
    if not manifest_path.exists() or not manifest_path.is_file():
        raise HTTPException(status_code=404, detail=f"Manifest file not found for pipeline '{pipeline_id}'. Ensure export has run.")
        
    from fastapi.responses import FileResponse
    # IMPLEMENTATION: Return the actual file using FastAPI's FileResponse
    return FileResponse(path=manifest_path, media_type='text/csv', filename=f'manifest_{pipeline_id}.csv')
