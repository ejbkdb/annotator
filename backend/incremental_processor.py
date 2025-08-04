# backend/incremental_processor.py
import logging
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy.orm import Session
import numpy as np
# IMPLEMENTATION: Added for real audio processing
import librosa 

from .pipeline_config import PipelineConfig
# IMPLEMENTATION: Import SQLAlchemy models from the new location
from .models_sqlalchemy import ProcessingHistory, Annotation, ProcessingResult
# IMPLEMENTATION: Import the actual client
from . import questdb_client 

# Configure logging
if not logging.getLogger().hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Configuration for feature extraction (Can be moved to config later if needed)
N_MFCC = 13
HOP_LENGTH = 512
N_FFT = 2048

def get_last_processed_timestamp(session: Session, pipeline_id: str, sensor: str) -> Optional[datetime]:
    """Retrieves the most recent SUCCESSFUL processed timestamp."""
    # IMPLEMENTATION: Real database query, checking for SUCCESS status
    last_run = session.query(ProcessingHistory).filter_by(
        pipeline_id=pipeline_id,
        sensor_id=sensor,
        status="SUCCESS" # Only rely on successful runs to determine the starting point
    ).order_by(ProcessingHistory.processed_end_utc.desc()).first()
    return last_run.processed_end_utc if last_run else None

def find_unprocessed_windows(config: PipelineConfig, session: Session):
    """Generates time windows that have not yet been processed."""
    unprocessed_windows = {}
    
    # IMPLEMENTATION: Ensure time ranges are parsed correctly and are timezone-aware (UTC)
    config_start_time = None
    if config.input.time_range.start:
        try:
            # Robust parsing of ISO format, ensuring UTC
            config_start_time = datetime.fromisoformat(config.input.time_range.start.replace('Z', '+00:00'))
        except ValueError:
            logging.error(f"Invalid start time format in config: {config.input.time_range.start}")
            return {}
        
    # If end time is not specified, use the current time in UTC
    config_end_time = datetime.now(timezone.utc)
    if config.input.time_range.end:
        try:
            config_end_time = datetime.fromisoformat(config.input.time_range.end.replace('Z', '+00:00'))
        except ValueError:
             logging.error(f"Invalid end time format in config: {config.input.time_range.end}")
             return {}

    for sensor in config.input.collections:
        unprocessed_windows[sensor] = []
        last_processed_ts = get_last_processed_timestamp(session, config.pipeline_id, sensor)
        
        # Determine the start time for this run
        start_time = config_start_time
        
        if last_processed_ts:
            # Start from the last processed point, unless the config start is later
            start_time = last_processed_ts if not start_time else max(start_time, last_processed_ts)
        
        if not start_time:
            # If there's no history and no start time in config, we can't process.
            logging.warning(f"Skipping sensor {sensor}: No processing history and no start time defined in pipeline configuration.")
            continue

        # Generate new windows using timestamps for calculation
        window_size_s = config.processing.window_size_seconds
        step_size_s = window_size_s - config.processing.overlap_seconds
        
        current_start_ts = start_time.timestamp()
        end_ts = config_end_time.timestamp()

        while current_start_ts + window_size_s <= end_ts:
            # Convert timestamps back to timezone-aware datetime objects (UTC)
            window_start_dt = datetime.fromtimestamp(current_start_ts, tz=timezone.utc)
            window_end_dt = datetime.fromtimestamp(current_start_ts + window_size_s, tz=timezone.utc)
            
            unprocessed_windows[sensor].append((window_start_dt, window_end_dt))
            current_start_ts += step_size_s
            
    return unprocessed_windows

def find_overlapping_annotations(session: Session, sensor: str, window_start: datetime, window_end: datetime) -> List[Annotation]:
    """Finds existing annotations that overlap with the given processing window."""
    # IMPLEMENTATION: Real SQL query against the Annotation table using SQLAlchemy ORM
    # The logic (StartA < EndB AND EndA > StartB) ensures overlap detection.
    annotations = session.query(Annotation).filter(
        Annotation.sensor == sensor,
        Annotation.start_timestamp < window_end,
        Annotation.end_timestamp > window_start
    ).all()
    return annotations

# IMPLEMENTATION: Real feature extraction function
def extract_features(audio_data: np.ndarray, sample_rate: int) -> dict:
    """Performs actual audio feature extraction using librosa."""
    if audio_data.size == 0:
        logging.warning("Audio data is empty, skipping feature extraction.")
        return {"rms": None, "zcr": None, "mfcc_mean": None}

    # Ensure audio data is float32 for librosa
    if audio_data.dtype != np.float32:
        # Normalize int16 data (common for WAV/FLAC) to float [-1.0, 1.0]
        if np.issubdtype(audio_data.dtype, np.integer):
            max_val = np.iinfo(audio_data.dtype).max
            audio_data = audio_data.astype(np.float32) / max_val
        else:
            audio_data = audio_data.astype(np.float32)

    try:
        # 1. RMS Energy
        rms = np.mean(librosa.feature.rms(y=audio_data))
        
        # 2. Zero Crossing Rate
        zcr = np.mean(librosa.feature.zero_crossing_rate(y=audio_data))
        
        # 3. MFCCs (Mel-Frequency Cepstral Coefficients)
        mfccs = librosa.feature.mfcc(y=audio_data, sr=sample_rate, n_mfcc=N_MFCC, n_fft=N_FFT, hop_length=HOP_LENGTH)
        # Calculate mean across time frames for a summary vector
        mfcc_mean = np.mean(mfccs, axis=1).tolist() 

        return {
            "rms": float(rms),
            "zcr": float(zcr),
            "mfcc_mean": mfcc_mean
        }
    except Exception as e:
        # Handle potential errors during DSP (e.g., invalid sample rates, corrupted audio)
        logging.error(f"Error during feature extraction: {e}", exc_info=True)
        return {"rms": None, "zcr": None, "mfcc_mean": None}

def run_pipeline_incrementally(config: PipelineConfig, session: Session):
    """Main function to run the incremental processing pipeline."""
    logging.info(f"Starting incremental processing for pipeline: {config.pipeline_id}")
    
    unprocessed_windows = find_unprocessed_windows(config, session)
    
    total_new_windows = sum(len(w) for w in unprocessed_windows.values())
    logging.info(f"Found {total_new_windows} new windows to process.")

    if total_new_windows == 0:
        logging.info("No new data to process. Pipeline run complete.")
        return

    # Process sensor by sensor to manage history updates correctly
    for sensor, windows in unprocessed_windows.items():
        if not windows:
            continue
            
        logging.info(f"Processing {len(windows)} new windows for sensor: {sensor}")
        
        # Track progress for the history entry
        run_start_time = datetime.utcnow()
        # Initialize tracking variables for this sensor run
        processed_start = windows[0][0]
        current_processed_end = processed_start # Tracks the furthest point successfully processed
        status = "SUCCESS"
        error_details = []
        windows_processed_count = 0

        try:
            for start_dt, end_dt in windows:
                # 1. Fetch data from QuestDB (REAL IMPLEMENTATION)
                try:
                    # Ensure timestamps are correctly formatted for the client
                    audio_samples = questdb_client.query_raw_audio_data(
                        sensor, 
                        start_dt.isoformat(), 
                        end_dt.isoformat()
                    )
                except Exception as e:
                    logging.error(f"Failed to fetch data for window {start_dt} - {end_dt} on sensor {sensor}: {e}")
                    status = "FAILED"
                    error_details.append(f"Fetch error at {start_dt}: {e}")
                    break # Stop processing this sensor if data fetching fails

                # 2. Find overlapping annotations (REAL IMPLEMENTATION)
                annotations = find_overlapping_annotations(session, sensor, start_dt, end_dt)
                
                # 3. Perform ML processing/feature extraction (REAL IMPLEMENTATION)
                try:
                    features = extract_features(audio_samples, config.processing.target_sample_rate)
                except Exception as e:
                    logging.error(f"Feature extraction failed for window {start_dt} on sensor {sensor}: {e}")
                    status = "FAILED"
                    error_details.append(f"Feature extraction error at {start_dt}: {e}")
                    break 
                
                # 4. Store results (REAL IMPLEMENTATION)
                # Link to the first overlapping annotation if multiple exist
                linked_annotation_id = annotations[0].id if annotations else None
                
                result_entry = ProcessingResult(
                    pipeline_id=config.pipeline_id,
                    sensor_id=sensor,
                    start_timestamp=start_dt,
                    end_timestamp=end_dt,
                    feature_rms=features['rms'],
                    feature_zcr=features['zcr'],
                    annotation_id=linked_annotation_id,
                    details_json={"mfcc_mean": features['mfcc_mean']}
                )
                session.add(result_entry)
                
                # Update the end time only if processing was successful
                current_processed_end = end_dt
                windows_processed_count += 1
            
            # Commit results for this sensor batch
            session.commit()

        except Exception as e:
            # Catch any unexpected errors during the loop (e.g., database connection loss)
            logging.error(f"Critical error during processing of sensor {sensor}: {e}", exc_info=True)
            session.rollback()
            status = "FAILED"
            error_details.append(f"Critical error: {e}")

        finally:
            # Update ProcessingHistory if any windows were processed or if the run failed after starting
            if windows_processed_count > 0 or (status == "FAILED" and len(windows) > 0):
                # If we failed partway, the status is PARTIAL (if we processed some) or FAILED (if none processed)
                if status == "FAILED" and windows_processed_count > 0:
                     status = "PARTIAL"

                # IMPLEMENTATION: Record the actual history of what happened
                history_entry = ProcessingHistory(
                    pipeline_id=config.pipeline_id,
                    sensor_id=sensor,
                    processed_start_utc=processed_start,
                    processed_end_utc=current_processed_end, # Use the actual end time reached
                    run_timestamp=run_start_time,
                    status=status,
                    details="\n".join(error_details) if error_details else None
                )
                session.add(history_entry)
                session.commit()

    logging.info("Incremental processing run finished and history updated.")
