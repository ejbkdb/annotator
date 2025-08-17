#!/bin/bash

# This script runs the bulk ingestion for all specified data sets.
# Ensure you are in the correct root directory where the 'backend' folder is located.

echo "--- Starting Bulk Data Ingestion ---"

# =========================
# ======== 7/16 ===========
# =========================

# --- No Foam Locations (7/16) ---
# echo "Processing 7/16: No Foam locations..."
# python -m backend.tests.run_bulk_ingest2 --folder-path "/srv/b8-data/standalone/716/regular_1/6131-3063/20250716/" --collection-name "l1_moth_no_foam"
# python -m backend.tests.run_bulk_ingest2 --folder-path "/srv/b8-data/standalone/716/regular_2/3031-3063/20250716/" --collection-name "l2_moth_no_foam"
# python -m backend.tests.run_bulk_ingest2 --folder-path "/srv/b8-data/standalone/716/regular_3/3031-3063/20250716/" --collection-name "l3_moth_no_foam"
# echo "Done with 7/16 No Foam locations."

# # --- Foam Locations (7/16) ---
# echo "Processing 7/16: Foam locations..."
# python -m backend.tests.run_bulk_ingest2 --folder-path "/srv/b8-data/standalone/716/foam_1/6431-3063/20250716/" --collection-name "l1_moth_foam"
# python -m backend.tests.run_bulk_ingest2 --folder-path "/srv/b8-data/standalone/716/foam_2/6231-3063/20250716/" --collection-name "l2_moth_foam"
# python -m backend.tests.run_bulk_ingest2 --folder-path "/srv/b8-data/standalone/716/foam_3/9016-4EF8/20250716/" --collection-name "l3_moth_foam"
# echo "Done with 7/16 Foam locations."

# (No case_* directories under 716)

# =========================
# ======== 7/17 ===========
# =========================

# # --- No Foam Locations (7/17) ---
echo "Processing 7/17: No Foam locations..."
python -m backend.tests.run_bulk_ingest2 --folder-path "/srv/b8-data/standalone/717/regular_1/20250717/" --collection-name "l1_moth_no_foam"
python -m backend.tests.run_bulk_ingest2 --folder-path "/srv/b8-data/standalone/717/regular_2/20250717/" --collection-name "l2_moth_no_foam"
python -m backend.tests.run_bulk_ingest2 --folder-path "/srv/b8-data/standalone/717/regular_3/20250717/" --collection-name "l3_moth_no_foam"
echo "Done with 7/17 No Foam locations."

# --- Foam Locations (7/17) ---
echo "Processing 7/17: Foam locations..."
python -m backend.tests.run_bulk_ingest2 --folder-path "/srv/b8-data/standalone/717/foam_1/20250717/" --collection-name "l1_moth_foam"
python -m backend.tests.run_bulk_ingest2 --folder-path "/srv/b8-data/standalone/717/foam_2/20250717/" --collection-name "l2_moth_foam"
python -m backend.tests.run_bulk_ingest2 --folder-path "/srv/b8-data/standalone/717/foam_3/20250717/" --collection-name "l3_moth_foam"
echo "Done with 7/17 Foam locations."

# --- Case Locations (7/17) ---
echo "Processing 7/17: Case locations..."
python -m backend.tests.run_bulk_ingest2 --folder-path "/srv/b8-data/standalone/717/case_1/20250717/" --collection-name "l1_case"
python -m backend.tests.run_bulk_ingest2 --folder-path "/srv/b8-data/standalone/717/case_2/20250717/" --collection-name "l2_case"
python -m backend.tests.run_bulk_ingest2 --folder-path "/srv/b8-data/standalone/717/case_3/20250717/" --collection-name "l3_case"
echo "Done with 7/17 Case locations."

# echo "--- Bulk Data Ingestion complete ---"
