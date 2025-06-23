# backend/database.py
import sqlite3
from models import Event

DATABASE_FILE = "test_range.db"

def init_db():
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("""CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, start_timestamp TEXT NOT NULL, end_timestamp TEXT NOT NULL, vehicle_type TEXT NOT NULL, vehicle_identifier TEXT, direction TEXT, annotator_notes TEXT);""")
    conn.commit()
    conn.close()

def save_event_to_db(event: Event):
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?)", (
        event.id,
        event.start_timestamp.isoformat(),
        event.end_timestamp.isoformat(),
        event.vehicle_type,
        event.vehicle_identifier,
        event.direction,
        event.annotator_notes
    ))
    conn.commit()
    conn.close()

def get_all_events_from_db() -> list[dict]:
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM events ORDER BY start_timestamp DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# backend/database.py