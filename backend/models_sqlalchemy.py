# backend/models_sqlalchemy.py
import os
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import declarative_base, relationship
import logging
from datetime import datetime

# Configure logging
# Use the root logger configuration if already set up, otherwise basicConfig.
if not logging.getLogger().hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Configuration ---
DATABASE_URL = os.environ.get("ANNOTATOR_DB_URL", "sqlite:///./annotation_system.db")

Base = declarative_base()

class ProcessingHistory(Base):
    """Tracks the progress of processing pipelines on a per-sensor basis."""
    __tablename__ = 'processing_history'
    id = Column(Integer, primary_key=True)
    pipeline_id = Column(String, nullable=False, index=True)
    sensor_id = Column(String, nullable=False, index=True)
    processed_start_utc = Column(DateTime, nullable=False)
    processed_end_utc = Column(DateTime, nullable=False)
    run_timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    # IMPLEMENTATION: Added status and details for robust tracking
    status = Column(String, default="SUCCESS") # SUCCESS, FAILED, PARTIAL
    details = Column(Text, nullable=True)
    
    def __repr__(self):
        return f"<ProcessingHistory(pipeline='{self.pipeline_id}', sensor='{self.sensor_id}', status='{self.status}')>"

class PipelineConfiguration(Base):
    """Stores JSON configurations for different pipelines."""
    __tablename__ = 'pipeline_configurations'
    id = Column(Integer, primary_key=True)
    pipeline_id = Column(String, unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    config_json = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<PipelineConfiguration(id='{self.pipeline_id}')>"

class SensorMetadata(Base):
    """Stores metadata about each physical sensor or data collection."""
    __tablename__ = 'sensor_metadata'
    id = Column(Integer, primary_key=True)
    collection_name = Column(String, unique=True, nullable=False, index=True)
    ingest_date = Column(DateTime, default=datetime.utcnow)
    location = Column(String, nullable=True)
    hardware_id = Column(String, nullable=True)
    # IMPLEMENTATION: Added sample rate tracking
    sample_rate = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)

    def __repr__(self):
        return f"<SensorMetadata(collection='{self.collection_name}')>"

# Concrete Annotation table for the advanced system.
class Annotation(Base):
    __tablename__ = 'annotations'
    id = Column(String, primary_key=True)
    # IMPLEMENTATION: Added indexes for time-based queries
    start_timestamp = Column(DateTime, nullable=False, index=True)
    end_timestamp = Column(DateTime, nullable=False, index=True)
    sensor = Column(String, nullable=False, index=True)
    vehicle_type = Column(String)
    action = Column(String)
    location = Column(String)
    status = Column(String, default="manual")
    parent_event_id = Column(String, nullable=True)
    notes = Column(Text)

# IMPLEMENTATION: New table to store results of processing (features, classifications)
class ProcessingResult(Base):
    __tablename__ = 'processing_results'
    id = Column(Integer, primary_key=True)
    pipeline_id = Column(String, nullable=False, index=True)
    sensor_id = Column(String, nullable=False, index=True)
    start_timestamp = Column(DateTime, nullable=False, index=True)
    end_timestamp = Column(DateTime, nullable=False)
    
    # Example features extracted during processing
    feature_rms = Column(Float, nullable=True)
    feature_zcr = Column(Float, nullable=True)
    
    # IMPLEMENTATION: Real Foreign Key relationship
    annotation_id = Column(String, ForeignKey('annotations.id'), nullable=True)
    annotation = relationship("Annotation")

    # For storing complex features like MFCC vectors or model outputs
    details_json = Column(JSON, nullable=True) 


def apply_migrations():
    """Connects to the database and creates all defined tables."""
    logging.info(f"Connecting to database: {DATABASE_URL}")
    try:
        # Determine connection arguments based on DB type
        connect_args = {}
        if DATABASE_URL.startswith("sqlite"):
            # Necessary for SQLite in multi-threaded environments (like FastAPI)
            connect_args = {"check_same_thread": False}
            
        engine = create_engine(DATABASE_URL, connect_args=connect_args)
        logging.info("Applying migrations...")
        # IMPLEMENTATION: Creates all tables defined in Base metadata
        Base.metadata.create_all(engine)
        logging.info("All tables created or verified successfully.")
    except Exception as e:
        logging.error(f"Failed to apply migrations: {e}")
        # IMPLEMENTATION: Real error handling
        raise

if __name__ == "__main__":
    apply_migrations()
