# backend/main.py
import uuid
import json
import os
from datetime import datetime
from typing import List

from fastapi import FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from models import Event, EventPayload, VehicleConfig, Convoy, ConvoyCreationPayload, ConvoyUpdatePayload
import database

app = FastAPI(title="Test Range Annotation API")

# Middleware and startup events are unchanged...
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
    os.makedirs("data/convoys", exist_ok=True)


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
    """Creates a single event. Can be a standalone event or linked to a convoy."""
    # FIX: Reverted to .dict() for Pydantic V1 compatibility
    event = Event(id=str(uuid.uuid4()), **payload.dict())
    try:
        database.save_event_to_db(event)
    except Exception as e:
        print(f"Error creating event: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {e}")
    return event

@app.post("/api/convoys", response_model=Convoy, status_code=201, tags=["Convoys"])
async def create_convoy(payload: ConvoyCreationPayload):
    """Creates a new convoy record and returns its details including the new ID."""
    new_convoy = Convoy(
        id=str(uuid.uuid4()),
        created_at=datetime.now(),
        # FIX: Reverted to .dict() for Pydantic V1 compatibility
        **payload.dict()
    )
    try:
        database.save_convoy_to_db(new_convoy)
    except Exception as e:
        print(f"Error creating convoy record: {e}")
        raise HTTPException(status_code=500, detail=f"Database error on convoy creation: {e}")
    return new_convoy

@app.put("/api/convoys/{convoy_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Convoys"])
async def update_convoy(convoy_id: str, payload: ConvoyUpdatePayload):
    """Updates the metadata for an existing convoy."""
    if not database.update_convoy_in_db(convoy_id, payload):
        raise HTTPException(status_code=404, detail=f"Convoy with id {convoy_id} not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.delete("/api/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Events"])
async def delete_event(event_id: str):
    if not database.delete_event_from_db(event_id):
        raise HTTPException(status_code=404, detail=f"Event with id {event_id} not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)