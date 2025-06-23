# backend/main.py
import uuid
import json
import os
from datetime import datetime
from typing import List

from fastapi import FastAPI, HTTPException
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

# backend/main.py