#!/bin/bash

# This script runs the bulk ingestion for all Florida data sets.
# Ensure you're in /home/eborcherding/Documents/florida/florida_v3/

echo "--- Starting Florida Bulk Data Ingestion ---"

# --- L1 Locations ---
echo "Processing: L1 locations..."
python -m backend.tests.run_bulk_ingest2 --folder-path "/home/eborcherding/Documents/florida/florida_v3/l1_green_2/" --collection-name "l1_green_2"
python -m backend.tests.run_bulk_ingest2 --folder-path "/home/eborcherding/Documents/florida/florida_v3/l1_no_foam/" --collection-name "l1_no_foam"
echo "Done with L1."

# --- L2 Locations ---
echo "Processing: L2 locations..."
python -m backend.tests.run_bulk_ingest2 --folder-path "/home/eborcherding/Documents/florida/florida_v3/l2_case_1/" --collection-name "l2_case_1"
python -m backend.tests.run_bulk_ingest2 --folder-path "/home/eborcherding/Documents/florida/florida_v3/l2_no_foam/" --collection-name "l2_no_foam"
# python -m backend.tests.run_bulk_ingest2 --folder-path "/home/eborcherding/Documents/florida/florida_v3/l2_shake/" --collection-name "l2_shake"
echo "Done with L2."

# --- L3 Locations ---
echo "Processing: L3 locations..."
python -m backend.tests.run_bulk_ingest2 --folder-path "/home/eborcherding/Documents/florida/florida_v3/l3_case_1/" --collection-name "l3_case_1"
python -m backend.tests.run_bulk_ingest2 --folder-path "/home/eborcherding/Documents/florida/florida_v3/l3_foam/" --collection-name "l3_foam"
python -m backend.tests.run_bulk_ingest2 --folder-path "/home/eborcherding/Documents/florida/florida_v3/l3_green_1/" --collection-name "l3_green_1"
python -m backend.tests.run_bulk_ingest2 --folder-path "/home/eborcherding/Documents/florida/florida_v3/l3_no_foam/" --collection-name "l3_no_foam"
# python -m backend.tests.run_bulk_ingest2 --folder-path "/home/eborcherding/Documents/florida/florida_v3/l3_shake/" --collection-name "l3_shake"
echo "Done with L3."

# --- L4 Locations ---
echo "Processing: L4 locations..."
python -m backend.tests.run_bulk_ingest2 --folder-path "/home/eborcherding/Documents/florida/florida_v3/l4_green_1/" --collection-name "l4_green_1"
python -m backend.tests.run_bulk_ingest2 --folder-path "/home/eborcherding/Documents/florida/florida_v3/l4_no_foam/" --collection-name "l4_no_foam"
# python -m backend.tests.run_bulk_ingest2 --folder-path "/home/eborcherding/Documents/florida/florida_v3/l4_shake/" --collection-name "l4_shake"
echo "Done with L4."

# --- Test Range ---
# echo "Processing: test_range.db (if applicable)..."
# Add command here if you have ingestion logic for DB files

echo "--- All Florida Ingestion Tasks Complete ---"
