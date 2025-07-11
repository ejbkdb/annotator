# backend/run_test_injest.py
import time
from multiprocessing import Pool, cpu_count
# Use the correct package import
from backend import questdb_client

# --- CONFIGURE YOUR TEST HERE ---
TEST_FILE_PATH = "/home/eborcherding/Documents/florida/test/24F319046484A67E_20250623_140000.WAV"
TEST_COLLECTION_NAME = "my_hardcoded_test"
# --------------------------------

# This is the standard guard for multiprocessing code.
if __name__ == "__main__":
    print("--- Starting Hardcoded Ingestion Test ---")
    
    # 1. Prepare the list of tasks to be executed.
    # This is a simple, synchronous call.
    print(f"Preparing tasks for file: {TEST_FILE_PATH}")
    tasks_to_run = questdb_client.prepare_ingestion_tasks(TEST_FILE_PATH, TEST_COLLECTION_NAME)
    
    # 2. Create and run the multiprocessing Pool.
    num_processes = max(1, cpu_count() - 1)
    print(f"Starting Pool with {num_processes} processes to handle {len(tasks_to_run)} chunks...")
    
    start_time = time.time()
    with Pool(processes=num_processes) as pool:
        # Pass the top-level, importable worker function to the pool.
        results = pool.map(questdb_client.ingest_worker, tasks_to_run)
    end_time = time.time()
    
    # 3. Report the results.
    total_written = sum(results)
    duration = end_time - start_time
    rate = total_written / duration if duration > 0 else 0
    
    print("-" * 20)
    print("--- Test Finished ---")
    print(f"Wrote {total_written:,} points in {duration:.2f} seconds ({rate:,.0f} points/sec).")