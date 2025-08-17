import sqlite3
from datetime import datetime, timedelta

def process_annotations(
    source_db_path,
    source_table_name,
    new_db_path,
    new_table_name,
    time_buffer_seconds=25,
):
    """
    Extracts annotations, adds a time buffer, and populates a new database.

    Args:
        source_db_path (str): Path to the source SQLite database.
        source_table_name (str): Name of the table to read from.
        new_db_path (str): Path for the new SQLite database to be created.
        new_table_name (str): Name of the table to be created in the new database.
        time_buffer_seconds (int, optional): Seconds to add/subtract from timestamps.
                                            Defaults to 25.
    """
    try:
        # Connect to the source database and read the data
        source_conn = sqlite3.connect(source_db_path)
        source_cursor = source_conn.cursor()
        source_cursor.execute(f"SELECT * FROM {source_table_name}")
        refined_annotations = source_cursor.fetchall()
        source_column_names = [
            description[0] for description in source_cursor.description
        ]
        source_conn.close()

        # Create a new database and table
        new_conn = sqlite3.connect(new_db_path)
        new_cursor = new_conn.cursor()

        # Define the schema for the new table, now including the 'status' column
        new_cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {new_table_name} (
                id TEXT PRIMARY KEY,
                parent_event_id TEXT,
                start_timestamp TEXT,
                end_timestamp TEXT,
                vehicle_id TEXT,
                vehicle_type TEXT,
                location TEXT,
                action TEXT,
                direction TEXT,
                annotation TEXT,
                source_cam TEXT,
                convoy_id TEXT,
                status TEXT
            )
        """
        )

        # Process and insert the data
        for row in refined_annotations:
            row_dict = dict(zip(source_column_names, row))

            # Add time buffer
            start_time = datetime.fromisoformat(
                row_dict["start_timestamp"]
            ) - timedelta(seconds=time_buffer_seconds)
            end_time = datetime.fromisoformat(
                row_dict["end_timestamp"]
            ) + timedelta(seconds=time_buffer_seconds)

            # Prepare the new row for insertion, including the status
            new_row = (
                row_dict.get("id"),
                row_dict.get("parent_event_id"),
                start_time.isoformat(),
                end_time.isoformat(),
                row_dict.get("vehicle_id"),
                row_dict.get("vehicle_type"),
                row_dict.get("location"),
                row_dict.get("action"),
                row_dict.get("direction"),
                row_dict.get("annotator_notes"),
                row_dict.get("source_cam"),
                None,  # for convoy_id
                "manual",  # for status
            )

            # Explicitly name columns in INSERT statement for clarity and robustness
            new_cursor.execute(
                f"""INSERT INTO {new_table_name} (
                        id, parent_event_id, start_timestamp, end_timestamp, vehicle_id,
                        vehicle_type, location, action, direction, annotation,
                        source_cam, convoy_id, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                new_row,
            )

        new_conn.commit()
        new_conn.close()

        print(f"Successfully created and populated '{new_db_path}'.")

    except sqlite3.Error as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    # --- Configuration ---

    SOURCE_DB = "/home/eborcherding/Documents/annotator/test_range_20250728.db"
    SOURCE_TABLE = "refined_annotations"
    NEW_DB = "/home/eborcherding/Documents/annotator/flv2.db"
    NEW_TABLE = "events"
    BUFFER_SECONDS = 25

    process_annotations(SOURCE_DB, SOURCE_TABLE, NEW_DB, NEW_TABLE, BUFFER_SECONDS)