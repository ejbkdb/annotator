# backend/database.py
import sqlite3
from .models import Event
from typing import Optional, List

DATABASE_FILE = "/home/eborcherding/Documents/annotator/test_range.db"

def init_db():
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    # Original events table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY, 
            start_timestamp TEXT NOT NULL, 
            end_timestamp TEXT NOT NULL, 
            vehicle_type TEXT NOT NULL, 
            vehicle_identifier TEXT, 
            direction TEXT, 
            annotator_notes TEXT,
            status TEXT NOT NULL DEFAULT 'manual'
        );
    """)
    # --- MODIFIED: Add source_collection column ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS refined_annotations (
            id TEXT PRIMARY KEY,
            parent_event_id TEXT NOT NULL,
            source_collection TEXT NOT NULL,
            start_timestamp TEXT NOT NULL,
            end_timestamp TEXT NOT NULL,
            vehicle_type TEXT NOT NULL,
            vehicle_subclass TEXT NOT NULL,
            location TEXT NOT NULL,
            action TEXT NOT NULL,
            direction TEXT NOT NULL,
            annotator_notes TEXT,
            FOREIGN KEY (parent_event_id) REFERENCES events (id)
        );
    """)
    try:
        cursor.execute("ALTER TABLE events ADD COLUMN status TEXT NOT NULL DEFAULT 'manual'")
    except sqlite3.OperationalError:
        pass
    # --- MODIFIED: Add source_collection column if it doesn't exist for backward compatibility ---
    try:
        cursor.execute("ALTER TABLE refined_annotations ADD COLUMN source_collection TEXT NOT NULL DEFAULT 'unknown'")
    except sqlite3.OperationalError:
        pass # Column already exists
    conn.commit()
    conn.close()

def save_event_to_db(event: Event):
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO events (id, start_timestamp, end_timestamp, vehicle_type, vehicle_identifier, direction, annotator_notes, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
        event.id, event.start_timestamp.isoformat(), event.end_timestamp.isoformat(),
        event.vehicle_type, event.vehicle_identifier, event.direction,
        event.annotator_notes, event.status
    ))
    conn.commit()
    conn.close()

# --- MODIFIED: Update INSERT statement to include source_collection ---
def save_refined_annotation_to_db(annotation_data: dict):
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO refined_annotations 
        (id, parent_event_id, source_collection, start_timestamp, end_timestamp, vehicle_type, vehicle_subclass, location, action, direction, annotator_notes)
        VALUES (:id, :parent_event_id, :source_collection, :start_timestamp, :end_timestamp, :vehicle_type, :vehicle_subclass, :location, :action, :direction, :annotator_notes)
    """, annotation_data)
    conn.commit()
    conn.close()
    return get_refined_annotation_by_id(annotation_data['id'])


def get_all_events_from_db(status: Optional[str] = None) -> list[dict]:
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    query = "SELECT * FROM events"
    params = []
    if status:
        query += " WHERE status = ?"
        params.append(status)
    query += " ORDER BY start_timestamp DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def delete_event_from_db(event_id: str) -> bool:
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM events WHERE id = ?", (event_id,))
    conn.commit()
    deleted_rows = cursor.rowcount
    conn.close()
    return deleted_rows > 0

def update_event_status_in_db(event_id: str, new_status: str) -> bool:
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE events SET status = ? WHERE id = ?", (new_status, event_id))
    conn.commit()
    updated_rows = cursor.rowcount
    conn.close()
    return updated_rows > 0

def get_event_by_id_from_db(event_id: str) -> dict | None:
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM events WHERE id = ?", (event_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def delete_children_and_reset_parent_event(parent_event_id: str) -> bool:
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM refined_annotations WHERE parent_event_id = ?", (parent_event_id,))
        cursor.execute("UPDATE events SET status = 'manual' WHERE id = ?", (parent_event_id,))
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        conn.rollback()
        print(f"Error during reset transaction: {e}")
        return False
    finally:
        conn.close()

def get_refined_annotations_by_parent_id(parent_event_id: str) -> List[dict]:
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM refined_annotations WHERE parent_event_id = ? ORDER BY start_timestamp ASC", (parent_event_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_refined_annotation_by_id(annotation_id: str) -> dict | None:
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM refined_annotations WHERE id = ?", (annotation_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None