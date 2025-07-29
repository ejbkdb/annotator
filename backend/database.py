# backend/database.py
import sqlite3
from models import Event, Convoy, ConvoyUpdatePayload

DATABASE_FILE = "test_range.db"

def init_db():
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            start_timestamp TEXT NOT NULL,
            end_timestamp TEXT NOT NULL,
            vehicle_type TEXT NOT NULL,
            vehicle_identifier TEXT,
            direction TEXT,
            annotator_notes TEXT,
            convoy_id TEXT,
            vehicle_action TEXT, -- The action column
            FOREIGN KEY (convoy_id) REFERENCES convoys(id)
        );
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS convoys (
            id TEXT PRIMARY KEY,
            convoy_number TEXT NOT NULL,
            convoy_spacing_seconds INTEGER,
            direction TEXT,
            notes TEXT,
            created_at TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()

def save_event_to_db(event: Event):
    """Saves a single event to the database, including its action."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    # --- THIS IS THE FIX ---
    # The INSERT statement now correctly includes the vehicle_action column
    # and expects 9 values to be provided.
    cursor.execute("""
        INSERT INTO events 
        (id, start_timestamp, end_timestamp, vehicle_type, vehicle_identifier, direction, annotator_notes, convoy_id, vehicle_action) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        event.id,
        event.start_timestamp.isoformat(),
        event.end_timestamp.isoformat(),
        event.vehicle_type,
        event.vehicle_identifier,
        event.direction,
        event.annotator_notes,
        event.convoy_id,
        event.vehicle_action
    ))
    conn.commit()
    conn.close()

def save_convoy_to_db(convoy: Convoy):
    """Saves the metadata of a new convoy to the database."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO convoys (id, convoy_number, convoy_spacing_seconds, direction, notes, created_at) VALUES (?, ?, ?, ?, ?, ?)", (
        convoy.id,
        convoy.convoy_number,
        convoy.convoy_spacing_seconds,
        convoy.direction,
        convoy.notes,
        convoy.created_at.isoformat()
    ))
    conn.commit()
    conn.close()

def update_convoy_in_db(convoy_id: str, payload: ConvoyUpdatePayload) -> bool:
    """Updates an existing convoy's metadata in the database."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    update_fields = {k: v for k, v in payload.dict().items() if v is not None}
    
    if not update_fields:
        conn.close()
        return True

    set_clause = ", ".join([f"{key} = ?" for key in update_fields.keys()])
    values = list(update_fields.values())
    values.append(convoy_id)

    cursor.execute(f"UPDATE convoys SET {set_clause} WHERE id = ?", tuple(values))
    conn.commit()
    updated_rows = cursor.rowcount
    conn.close()
    return updated_rows > 0

def get_all_events_from_db() -> list[dict]:
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM events ORDER BY start_timestamp DESC")
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