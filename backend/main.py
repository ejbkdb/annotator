# backend/main.py
import uuid
import json
import os
from datetime import datetime
from typing import List

from fastapi import FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from models import Event, EventPayload, VehicleConfig
import database

app = FastAPI(title="Test Range Annotation API")

# IMPORTANT: The port 5173 is the default for Vite.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    database.init_db()
    os.makedirs("data/events", exist_ok=True)

@app.get("/api/health", tags=["Status"])
async def health_check():
    return {"status": "ok"}

@app.get("/api/config/vehicles", response_model=List[VehicleConfig], tags=["Configuration"])
async def get_vehicle_config():
    try:
        with open("vehicles.json", "r") as f:
            return json.load(f)
    except Exception:
        raise HTTPException(500, "Error with vehicles.json")

@app.get("/api/events", response_model=List[Event], tags=["Events"])
async def get_all_events():
    return database.get_all_events_from_db()

@app.post("/api/events", response_model=Event, status_code=201, tags=["Events"])
async def create_event(payload: EventPayload):
    event = Event(id=str(uuid.uuid4()), **payload.dict())
    try:
        database.save_event_to_db(event)
        file_path = f"data/events/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{event.id}.json"
        with open(file_path, 'w') as f:
            json.dump(json.loads(event.json()), f, indent=4)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {e}")
    return event

@app.delete("/api/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Events"])
async def delete_event(event_id: str):
    # First, delete from the database
    if not database.delete_event_from_db(event_id):
        raise HTTPException(status_code=404, detail=f"Event with id {event_id} not found.")

    # Second, delete the corresponding JSON file.
    # We must search for it since the creation timestamp isn't stored.
    event_file_deleted = False
    events_dir = "data/events"
    try:
        for filename in os.listdir(events_dir):
            if filename.endswith(f"_{event_id}.json"):
                file_path = os.path.join(events_dir, filename)
                os.remove(file_path)
                event_file_deleted = True
                break
        if not event_file_deleted:
            # This is not critical enough to fail the request, but worth noting.
            print(f"Warning: Deleted event {event_id} from DB, but no corresponding JSON file was found.")
    except Exception as e:
        # If file deletion fails, this is a server error.
        raise HTTPException(status_code=500, detail=f"Failed to delete event file: {e}")

    return Response(status_code=status.HTTP_204_NO_CONTENT)

# backend/main.py