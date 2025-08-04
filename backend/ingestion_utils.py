# backend/ingestion_utils.py
import os
import glob
import time
import logging
from multiprocessing import Pool, cpu_count
# IMPLEMENTATION: Import the actual client
from backend import questdb_client

# Setup logging
if not logging.getLogger().hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Default patterns to look for
FILE_PATTERNS = ["*.WAV", "*.wav"]

def get_wav_files(folder_path):
    """Get all WAV files matching the patterns in the specified folder (non-recursive)."""
    # IMPLEMENTATION: Real file system check
    if not os.path.isdir(folder_path):
        logging.error(f"Directory not found: {folder_path}")
        raise FileNotFoundError(f"Directory not found: {folder_path}")
        
    wav_files = []
    # IMPLEMENTATION: Real file discovery using glob
    for pattern in FILE_PATTERNS:
        search_path = os.path.join(folder_path, pattern)
        wav_files.extend(glob.glob(search_path))
        
    wav_files.sort()
    return wav_files

def process_single_file(file_path, collection_name):
    """Process a single WAV file using multiprocessing and return statistics."""
    logging.info(f"Processing file: {os.path.basename(file_path)}")
    
    try:
        # 1. Prepare tasks (Read file, chunk data, generate timestamps)
        # IMPLEMENTATION: Real task preparation using the client's logic
        tasks_to_run = questdb_client.prepare_ingestion_tasks(file_path, collection_name)
        
        if not tasks_to_run:
            logging.warning(f"No tasks generated for {os.path.basename(file_path)}")
            return 0, 0
        
        # 2. Execute tasks using multiprocessing Pool
        num_processes = max(1, cpu_count() - 1)
        
        start_time = time.time()
        # IMPLEMENTATION: Real parallel execution of ingestion workers
        # Note: Initializing the Pool here is necessary for CLI scripts. 
        # For FastAPI background tasks, this must be handled carefully to avoid issues with process spawning.
        with Pool(processes=num_processes) as pool:
            # The ingest_worker must be defined at the top level of the questdb_client module
            results = pool.map(questdb_client.ingest_worker, tasks_to_run)
        end_time = time.time()
        
        total_written = sum(results)
        duration = end_time - start_time
        
        logging.info(f"Finished {os.path.basename(file_path)}: {total_written:,} points in {duration:.2f}s")
        return total_written, duration
        
    except Exception as e:
        # IMPLEMENTATION: Real error logging
        logging.error(f"Error processing {os.path.basename(file_path)}: {str(e)}", exc_info=True)
        return 0, 0

def run_bulk_ingestion(folder_path, collection_name):
    """Ingests all WAV files in a folder into the specified collection."""
    logging.info(f"Starting bulk ingestion for '{collection_name}' from '{folder_path}'")
    try:
        wav_files = get_wav_files(folder_path)
    except FileNotFoundError:
        return 0, 0
    
    if not wav_files:
        logging.warning("No WAV files found.")
        return 0, 0
        
    logging.info(f"Found {len(wav_files)} files to process.")
    
    overall_start_time = time.time()
    total_points = 0
    successful_files = 0
    
    # Process files sequentially, utilizing parallel processing within each file
    for i, file_path in enumerate(wav_files, 1):
        logging.info(f"[{i}/{len(wav_files)}] Ingesting {os.path.basename(file_path)}...")
        # IMPLEMENTATION: Call the real processing function
        points_written, _ = process_single_file(file_path, collection_name)
        
        if points_written > 0:
            successful_files += 1
            total_points += points_written
            
    overall_duration = time.time() - overall_start_time
    logging.info(f"Bulk ingestion complete. Success: {successful_files}/{len(wav_files)}. Total points: {total_points:,}. Duration: {overall_duration:.2f}s.")
    return total_points, successful_files
