# export_events_to_csv.py
import sqlite3
import csv
import os

# --- CONFIGURATION ---
DATABASE_FILE = "/home/eborcherding/Documents/annotator/annotator/test_range.db"
OUTPUT_CSV_FILE = "annotated_events.csv"
# ---------------------

def export_to_csv():
    """Exports the events table from the SQLite database to a CSV file."""
    print(f"Connecting to database: {DATABASE_FILE}")
    if not os.path.exists(DATABASE_FILE):
        print(f"ERROR: Database file not found at '{DATABASE_FILE}'")
        return

    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()

        print("Executing query: SELECT * FROM events")
        cursor.execute("SELECT * FROM events")

        rows = cursor.fetchall()
        
        if not rows:
            print("No events found in the database.")
            return

        headers = [description[0] for description in cursor.description]

        print(f"Writing {len(rows)} events to '{OUTPUT_CSV_FILE}'...")
        with open(OUTPUT_CSV_FILE, 'w', newline='') as csvfile:
            csv_writer = csv.writer(csvfile)
            # Write headers
            csv_writer.writerow(headers)
            # Write data rows
            csv_writer.writerows(rows)
        
        print("--- Export Complete ---")
        print(f"Successfully exported {len(rows)} events.")
        print("Next steps: Open 'annotated_events.csv' and add 'location' and 'activity' columns.")

    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == "__main__":
    export_to_csv()