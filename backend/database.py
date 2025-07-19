# backend/database.py
import sqlite3
from .models import Event
from typing import Optional

DATABASE_FILE = "/home/eborcherding/Documents/annotator/annotator/test_range.db"

def init_db():
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    # Added the 'status' column with a default value
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
    # Add status column if it doesn't exist (for backward compatibility)
    try:
        cursor.execute("ALTER TABLE events ADD COLUMN status TEXT NOT NULL DEFAULT 'manual'")
    except sqlite3.OperationalError:
        pass # Column already exists
    conn.commit()
    conn.close()

def save_event_to_db(event: Event):
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO events (id, start_timestamp, end_timestamp, vehicle_type, vehicle_identifier, direction, annotator_notes, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
        event.id,
        event.start_timestamp.isoformat(),
        event.end_timestamp.isoformat(),
        event.vehicle_type,
        event.vehicle_identifier,
        event.direction,
        event.annotator_notes,
        event.status
    ))
    conn.commit()
    conn.close()

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
    """Deletes an event from the database by its ID. Returns True if a row was deleted, False otherwise."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM events WHERE id = ?", (event_id,))
    conn.commit()
    deleted_rows = cursor.rowcount
    conn.close()
    return deleted_rows > 0

def update_event_status_in_db(event_id: str, new_status: str) -> bool:
    """Updates the status of an event. Returns True if a row was updated, False otherwise."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE events SET status = ? WHERE id = ?", (new_status, event_id))
    conn.commit()
    updated_rows = cursor.rowcount
    conn.close()
    return updated_rows > 0

def get_event_by_id_from_db(event_id: str) -> dict | None:
    """Fetches a single event by its ID."""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM events WHERE id = ?", (event_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

# backend/database.py