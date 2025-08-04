# backend/database_migrations.py
import os
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, JSON
from sqlalchemy.orm import declarative_base
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Configuration ---
# Use an environment variable or a default path for the database
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
    
    def __repr__(self):
        return f"<ProcessingHistory(pipeline='{self.pipeline_id}', sensor='{self.sensor_id}', end='{self.processed_end_utc.isoformat()}')>"

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
    notes = Column(Text, nullable=True)

    def __repr__(self):
        return f"<SensorMetadata(collection='{self.collection_name}', location='{self.location}')>"

# Dummy Annotation table for other modules to work.
# In a real system, this would likely already exist.
class Annotation(Base):
    __tablename__ = 'annotations'
    id = Column(String, primary_key=True)
    start_timestamp = Column(DateTime, nullable=False)
    end_timestamp = Column(DateTime, nullable=False)
    sensor = Column(String, nullable=False)
    vehicle_type = Column(String)
    action = Column(String)
    location = Column(String)


def apply_migrations():
    """Connects to the database and creates all defined tables."""
    logging.info(f"Connecting to database: {DATABASE_URL}")
    try:
        engine = create_engine(DATABASE_URL)
        logging.info("Applying migrations...")
        Base.metadata.create_all(engine)
        logging.info("All tables created or verified successfully.")
    except Exception as e:
        logging.error(f"Failed to apply migrations: {e}")
        raise

if __name__ == "__main__":
    apply_migrations()