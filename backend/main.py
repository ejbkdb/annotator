# backend/main.py
import uuid
import json
import os
import asyncio
from datetime import datetime
from typing import List
from pathlib import Path
from fastapi import FastAPI, HTTPException, Response, status, APIRouter, File, UploadFile, Form, BackgroundTasks

from fastapi.middleware.cors import CORSMiddleware
from .models import Event, EventPayload, VehicleConfig
from backend import database

# --- THIS IS THE ONLY CHANGE IN THIS FILE ---
# import influx_client 
from backend import questdb_client # Direct replacement, no alias.
# --- END OF CHANGE ---

import io
import wave
import struct
from fastapi.responses import StreamingResponse
import soundfile as sf
import numpy as np

PROJECT_ROOT = Path(__file__).parent
app = FastAPI(title="Test Range Annotation API")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

TEMP_UPLOAD_DIR = PROJECT_ROOT / "data" / "uploads"

@app.on_event("startup")
async def startup_event():
    database.init_db()
    os.makedirs(PROJECT_ROOT / "data" / "events", exist_ok=True)
    os.makedirs(TEMP_UPLOAD_DIR, exist_ok=True)

router_status = APIRouter(tags=["Status"])
router_config = APIRouter(tags=["Configuration"])
router_events = APIRouter(tags=["Events"])
router_audio = APIRouter(tags=["Audio & Timeseries"])

@router_config.get("/api/config/vehicles", response_model=List[VehicleConfig])
async def get_vehicle_config():
    try:
        with open(PROJECT_ROOT / "vehicles.json", "r") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(500, f"Error with vehicles.json: {e}")

async def process_and_ingest_files(collection_name: str, filenames: List[str]):
    print(f"--- BACKGROUND TASK STARTED for collection: '{collection_name}' with {len(filenames)} files. ---")
    successful_files, failed_files = 0, 0
    for i, filename in enumerate(filenames, 1):
        file_path = os.path.join(TEMP_UPLOAD_DIR, filename)
        if not os.path.exists(file_path):
            failed_files += 1; continue
        try:
            # Calls the new questdb_client module
            await questdb_client.ingest_wav_data_async(file_path, collection_name)
            successful_files += 1
        except Exception as e:
            failed_files += 1
        finally:
            if os.path.exists(file_path): os.remove(file_path)
    
    print(f"--- BACKGROUND TASK FINISHED --- [Successful: {successful_files}, Failed: {failed_files}]")

@router_audio.post("/api/audio/ingest", status_code=status.HTTP_202_ACCEPTED)
async def ingest_audio_files_optimized(background_tasks: BackgroundTasks, collection_name: str = Form(...), filenames: List[str] = Form(...)):
    background_tasks.add_task(process_and_ingest_files, collection_name, filenames)
    return {"message": f"Accepted. Ingestion for {len(filenames)} files into '{collection_name}' has started."}

@router_audio.post("/api/audio/upload")
async def upload_audio_files(files: List[UploadFile] = File(...)):
    saved_files = []
    for file in files:
        if not file.filename.lower().endswith(".wav"):
            raise HTTPException(status_code=400, detail="Invalid file type. Only .wav supported.")
        file_path = os.path.join(TEMP_UPLOAD_DIR, file.filename)
        with open(file_path, "wb") as buffer:
            buffer.write(await file.read())
        saved_files.append(file.filename)
    return {"filenames": saved_files, "message": f"Successfully uploaded {len(saved_files)} files."}

@router_audio.get("/api/audio/collections", response_model=List[str])
async def list_collections():
    return questdb_client.get_collections()

@router_audio.get("/api/audio/waveform")
async def get_waveform_data(collection: str, start: str, end: str, points: int = 2000):
    return questdb_client.query_waveform_data(collection, start, end, points)

@router_status.get("/api/health")
async def health_check(): return {"status": "ok"}
@router_events.get("/api/events", response_model=List[Event])
async def get_all_events(): return database.get_all_events_from_db()
@router_events.post("/api/events", response_model=Event, status_code=201)
async def create_event(payload: EventPayload):
    event = Event(id=str(uuid.uuid4()), **payload.dict())
    database.save_event_to_db(event)
    return event
@router_events.delete("/api/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(event_id: str):
    if not database.delete_event_from_db(event_id):
        raise HTTPException(status_code=404, detail="Event not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router_audio.get("/api/audio/collections/{collection_name}/info")
async def get_collection_info(collection_name: str):
    time_range = questdb_client.get_collection_time_range(collection_name)
    if not time_range:
        raise HTTPException(status_code=404, detail=f"No data found for collection '{collection_name}'.")
    return {"time_range": time_range}

@router_audio.get("/api/audio/raw")
async def get_raw_audio_clip(collection: str, start: str, end: str):
    SAMPLE_RATE = 48000
    np_samples = questdb_client.query_raw_audio_data(collection, start, end)
    if np_samples.size == 0:
        raise HTTPException(status_code=404, detail="No audio data found for the requested range.")
    buffer = io.BytesIO()
    sf.write(buffer, np_samples, samplerate=SAMPLE_RATE, format='WAV', subtype='PCM_16')
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="audio/wav")

app.include_router(router_status)
app.include_router(router_config)
app.include_router(router_events)
app.include_router(router_audio)