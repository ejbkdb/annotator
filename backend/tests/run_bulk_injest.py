# backend/run_bulk_ingest.py
import os
import glob
import time
from multiprocessing import Pool, cpu_count
# Use the correct package import
from backend import questdb_client

# --- CONFIGURE YOUR BULK INGESTION HERE ---
FOLDER_PATH = "/home/pbelous/Documents/regular_1/6131-3063/20250716/"
COLLECTION_NAME = "L1_moth_no_foam"

FOLDER_PATH = "/home/pbelous/Documents/regular_2/3031-3063/20250716/"
COLLECTION_NAME = "L2_moth_no_foam"

FOLDER_PATH = "/home/pbelous/Documents/regular_3/3031-3063/20250716/"
COLLECTION_NAME = "L3_moth_no_foam"

FOLDER_PATH = "/home/pbelous/Documents/foam_1/6431-3063/20250716/"
COLLECTION_NAME = "L1_moth_foam"

FOLDER_PATH = "/home/pbelous/Documents/foam_2/6231-3063/20250716/"
COLLECTION_NAME = "L2_moth_foam"

FOLDER_PATH = "/home/pbelous/Documents/foam_3/9016-4EF8/20250716/"
COLLECTION_NAME = "L3_moth_foam"

# File pattern - change if needed (e.g., "*.WAV", "*.wav", "**/*.wav" for recursive)
FILE_PATTERN = "*.WAV"
# --------------------------------

def get_wav_files(folder_path, pattern="*.WAV"):
    """Get all WAV files matching the pattern in the specified folder."""
    search_path = os.path.join(folder_path, pattern)
    wav_files = glob.glob(search_path)
    
    # Sort files for consistent processing order
    wav_files.sort()
    
    return wav_files

def process_single_file(file_path, collection_name):
    """Process a single WAV file and return statistics."""
    print(f"Processing: {os.path.basename(file_path)}")
    
    try:
        # Prepare tasks for this file
        tasks_to_run = questdb_client.prepare_ingestion_tasks(file_path, collection_name)
        
        if not tasks_to_run:
            print(f"  No tasks generated for {os.path.basename(file_path)}")
            return 0, 0
        
        # Process tasks with multiprocessing
        num_processes = max(1, cpu_count() - 1)
        
        start_time = time.time()
        with Pool(processes=num_processes) as pool:
            results = pool.map(questdb_client.ingest_worker, tasks_to_run)
        end_time = time.time()
        
        total_written = sum(results)
        duration = end_time - start_time
        
        print(f"  ✓ {os.path.basename(file_path)}: {total_written:,} points in {duration:.2f}s")
        return total_written, duration
        
    except Exception as e:
        print(f"  ✗ Error processing {os.path.basename(file_path)}: {str(e)}")
        return 0, 0

# This is the standard guard for multiprocessing code.
if __name__ == "__main__":
    print("--- Starting Bulk WAV Ingestion ---")
    
    # Validate folder exists
    if not os.path.exists(FOLDER_PATH):
        print(f"Error: Folder '{FOLDER_PATH}' does not exist!")
        exit(1)
    
    # Get all WAV files
    wav_files = get_wav_files(FOLDER_PATH, FILE_PATTERN)
    
    if not wav_files:
        print(f"No WAV files found in '{FOLDER_PATH}' matching pattern '{FILE_PATTERN}'")
        exit(1)
    
    print(f"Found {len(wav_files)} WAV files to process:")
    for i, file_path in enumerate(wav_files, 1):
        print(f"  {i}. {os.path.basename(file_path)}")
    
    # Confirm before proceeding
    response = input(f"\nProceed with ingestion into collection '{COLLECTION_NAME}'? (y/N): ")
    if response.lower() != 'y':
        print("Aborted.")
        exit(0)
    
    # Process all files
    print("\n" + "="*50)
    print("Starting bulk ingestion...")
    print("="*50)
    
    overall_start_time = time.time()
    total_points = 0
    total_duration = 0
    successful_files = 0
    
    for i, file_path in enumerate(wav_files, 1):
        print(f"\n[{i}/{len(wav_files)}] Processing {os.path.basename(file_path)}...")
        
        points_written, file_duration = process_single_file(file_path, COLLECTION_NAME)
        
        if points_written > 0:
            successful_files += 1
            total_points += points_written
            total_duration += file_duration
    
    overall_end_time = time.time()
    overall_duration = overall_end_time - overall_start_time
    
    # Final summary
    print("\n" + "="*50)
    print("--- BULK INGESTION COMPLETE ---")
    print("="*50)
    print(f"Files processed: {successful_files}/{len(wav_files)}")
    print(f"Total points written: {total_points:,}")
    print(f"Total processing time: {total_duration:.2f}s")
    print(f"Overall elapsed time: {overall_duration:.2f}s")
    
    if total_duration > 0:
        avg_rate = total_points / total_duration
        print(f"Average ingestion rate: {avg_rate:,.0f} points/sec")
    
    if successful_files > 0:
        print(f"Average points per file: {total_points // successful_files:,}")
    
    print(f"Collection name: '{COLLECTION_NAME}'")