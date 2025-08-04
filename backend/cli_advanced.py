# backend/cli_advanced.py
import click
import os
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import logging

from .pipeline_config import PipelineConfig
from .incremental_processor import run_pipeline_incrementally
from .ml_export_advanced import export_data
# IMPLEMENTATION: Import models from the new location
from .models_sqlalchemy import apply_migrations, PipelineConfiguration, SensorMetadata, ProcessingHistory
# IMPLEMENTATION: Import the real ingestion utility
from .ingestion_utils import run_bulk_ingestion

# Configure logging
if not logging.getLogger().hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


# --- Database Setup ---
DATABASE_URL = os.environ.get("ANNOTATOR_DB_URL", "sqlite:///./annotation_system.db")
# Determine connection arguments based on DB type
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@click.group()
def cli():
    """A CLI for the production audio annotation system."""
    pass

@cli.command()
@click.option('--config', 'config_path', required=True, type=click.Path(exists=True), help='Path to the pipeline JSON config file.')
@click.option('--incremental/--full', default=True, help='Run in incremental mode (default) or full reprocessing mode.')
def process(config_path, incremental):
    """Process data according to a pipeline configuration."""
    click.echo(f"Processing data with config: {config_path}. Mode: {'Incremental' if incremental else 'Full'}")
    
    try:
        # IMPLEMENTATION: Real config loading
        config = PipelineConfig.from_json(config_path)
    except Exception as e:
        logging.error(f"Failed to load configuration: {e}")
        return
    
    db = SessionLocal()
    try:
        if not incremental:
            # IMPLEMENTATION: Full run clears history to force reprocessing (Real DB operation)
            click.echo("Full reprocessing requested. Clearing history for this pipeline.")
            db.query(ProcessingHistory).filter_by(pipeline_id=config.pipeline_id).delete()
            db.commit()

        # IMPLEMENTATION: Call the actual processor
        run_pipeline_incrementally(config, db)
    except Exception as e:
        logging.error(f"Processing failed: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()
    click.echo("Processing complete.")

@cli.command()
@click.option('--path', required=True, type=click.Path(exists=True, file_okay=False), help='Path to the directory of new sensor data.')
@click.option('--collection', required=True, help='The new collection/sensor name.')
@click.option('--auto-process/--no-auto-process', default=False, help='Automatically run all pipelines after ingestion.')
def add_sensor(path, collection, auto_process):
    """Ingest data for a new sensor and optionally process it."""
    click.echo(f"Adding new sensor '{collection}' from path: {path}")
    
    # IMPLEMENTATION: Run the actual ingestion logic
    try:
        click.echo("Starting data ingestion...")
        total_points, successful_files = run_bulk_ingestion(path, collection)
        click.echo(f"Ingestion complete. Points: {total_points:,}. Files: {successful_files}.")
    except Exception as e:
        logging.error(f"Ingestion failed: {e}", exc_info=True)
        click.echo("Ingestion failed. Check logs for details.")
        return
    
    db = SessionLocal()
    try:
        # IMPLEMENTATION: Update metadata in the database (Real DB operation)
        # Use merge for UPSERT functionality
        sensor_meta = SensorMetadata(collection_name=collection, notes=f"Ingested from path: {path}")
        db.merge(sensor_meta)
        db.commit()
        click.echo("Sensor metadata updated.")
        
        if auto_process:
            click.echo("Auto-processing enabled. Running all relevant pipelines...")
            # IMPLEMENTATION: Query and run actual pipelines
            pipelines = db.query(PipelineConfiguration).all()
            for p_config_db in pipelines:
                config_dict = p_config_db.config_json
                # Check if the new collection is relevant to this pipeline
                if collection in config_dict.get('input', {}).get('collections', []):
                    click.echo(f"-> Running pipeline: {p_config_db.pipeline_id}")
                    try:
                        config = PipelineConfig(**config_dict)
                        # IMPLEMENTATION: Call the actual processor
                        run_pipeline_incrementally(config, db)
                    except Exception as e:
                        logging.error(f"Failed to run pipeline {p_config_db.pipeline_id}: {e}", exc_info=True)
                        db.rollback() # Rollback changes from the failed pipeline run
    finally:
        db.close()
        
    click.echo("Sensor addition process complete.")
    
@cli.command()
@click.option('--config', 'config_path', required=True, type=click.Path(exists=True), help='Path to the base pipeline config for export.')
@click.option('--window-size', type=float, help='Override window size in seconds.')
@click.option('--overlap', type=float, help='Override overlap in seconds.')
@click.option('--incremental/--full', default=True, help='Run in incremental mode (default) or full export mode.')
def export(config_path, window_size, overlap, incremental):
    """Export ML-ready dataset based on a configuration."""
    try:
        config = PipelineConfig.from_json(config_path)
    except Exception as e:
        logging.error(f"Failed to load configuration: {e}")
        return
    
    # Override config with CLI arguments if provided
    if window_size is not None:
        config.processing.window_size_seconds = window_size
        click.echo(f"Overriding window size to: {window_size}s")
    if overlap is not None:
        config.processing.overlap_seconds = overlap
        click.echo(f"Overriding overlap to: {overlap}s")
        
    db = SessionLocal()
    try:
        # IMPLEMENTATION: Call the actual export function
        export_data(config, db, incremental=incremental)
    except Exception as e:
        logging.error(f"Export failed: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()
    click.echo("Export complete.")

@cli.command()
# IMPLEMENTATION: Specified required timestamp format
@click.option('--start', required=True, help='Start date for catchup (ISO format, e.g., "2024-06-01T00:00:00Z").')
@click.option('--end', required=True, help='End date for catchup (ISO format, e.g., "2024-06-30T23:59:59Z").')
@click.option('--pipeline', 'pipeline_id', required=True, help='The ID of the pipeline to run.')
def catchup(start, end, pipeline_id):
    """Run a pipeline over a specific historical time range."""
    db = SessionLocal()
    try:
        # IMPLEMENTATION: Real DB lookup
        p_config_db = db.query(PipelineConfiguration).filter_by(pipeline_id=pipeline_id).first()
        if not p_config_db:
            click.echo(f"Error: Pipeline '{pipeline_id}' not found in the database.")
            return

        config = PipelineConfig(**p_config_db.config_json)
        
        # IMPLEMENTATION: Validate and parse timestamps
        try:
            # Ensure they are parsed correctly (expecting ISO format)
            start_dt = datetime.fromisoformat(start)
            end_dt = datetime.fromisoformat(end)
        except ValueError:
            click.echo("Error: Invalid timestamp format. Use ISO format (e.g., '2024-06-01T00:00:00Z').")
            return

        # Modify the config in-memory for the catchup run
        # Note: The processor handles the time range defined in the config object.
        config.input.time_range.start = start_dt.isoformat()
        config.input.time_range.end = end_dt.isoformat()

        click.echo(f"Running catchup for pipeline '{pipeline_id}' from {start} to {end}.")
        # IMPLEMENTATION: Call the actual processor
        # Note: The processor will still respect previous history unless explicitly cleared, 
        # but it will ensure the defined range is covered.
        run_pipeline_incrementally(config, db)
        
    except Exception as e:
        logging.error(f"Catchup run failed: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()
    click.echo("Catchup run complete.")

@cli.command()
def initdb():
    """Initialize the database with required tables."""
    click.echo("Initializing database schema...")
    # IMPLEMENTATION: Calls the actual migration function
    apply_migrations()
    click.echo("Database initialized.")

if __name__ == '__main__':
    # IMPLEMENTATION: Ensure compatibility with multiprocessing when run as a script
    from multiprocessing import freeze_support
    freeze_support()
    cli()
