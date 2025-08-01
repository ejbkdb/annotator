#!/bin/bash

# This script runs the bulk ingestion for all specified data sets.
# Ensure you are in the correct root directory where the 'backend' folder is located.

echo "--- Starting Bulk Data Ingestion ---"

# --- No Foam Locations ---
echo "Processing: No Foam locations..."
python -m backend.tests.run_bulk_ingest2 --folder-path "/home/pbelous/Documents/717/regular_1/20250717/" --collection-name "l1_moth_no_foam"
python -m backend.tests.run_bulk_ingest2 --folder-path "/home/pbelous/Documents/717/regular_2/20250717/" --collection-name "l2_moth_no_foam"
python -m backend.tests.run_bulk_ingest2 --folder-path "/home/pbelous/Documents/717/regular_3/20250717/" --collection-name "l3_moth_no_foam"
echo "Done with No Foam locations."

# --- Foam Locations ---
echo "Processing: Foam locations..."
python -m backend.tests.run_bulk_ingest2 --folder-path "/home/pbelous/Documents/717/foam_1/20250717/" --collection-name "l1_moth_foam"
python -m backend.tests.run_bulk_ingest2 --folder-path "/home/pbelous/Documents/717/foam_2/20250717/" --collection-name "l2_moth_foam"
python -m backend.tests.run_bulk_ingest2 --folder-path "/home/pbelous/Documents/717/foam_3/20250717/" --collection-name "l3_moth_foam"
echo "Done with Foam locations."

# --- Case Locations ---
echo "Processing: Case locations..."
python -m backend.tests.run_bulk_ingest2 --folder-path "/home/pbelous/Documents/717/case_1/20250717/" --collection-name "l1_case"
python -m backend.tests.run_bulk_ingest2 --folder-path "/home/pbelous/Documents/717/case_2/20250717/" --collection-name "l2_case"
python -m backend.tests.run_bulk_ingest2 --folder-path "/home/pbelous/Documents/717/case_3/20250717/" --collection-name "l3_case"
echo "Done with Case locations."

echo "--- All Ingestion Tasks Complete ---"

python -m backend.tests.run_bulk_ingest2 --folder-path "/home/eborcherding/Documents/florida/aggregated_2025-07-16/" --collection-name "orin_moth_foam"
