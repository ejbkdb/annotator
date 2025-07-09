# backend/main.py - Updated to use optimized ingestion
import uuid
import json
import os
import asyncio
from datetime import datetime
from typing import List
from pathlib import Path
from fastapi import FastAPI, HTTPException, Response, status, APIRouter, File, UploadFile, Form, BackgroundTasks

from fastapi.middleware.cors import CORSMiddleware
from models import Event, EventPayload, VehicleConfig
import database

import influx_client
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

# --- OPTIMIZED: Background Worker Function ---
async def process_and_ingest_files(collection_name: str, filenames: List[str]):
    """Optimized background processing using librosa and batched writes."""
    print(f"--- FAST BACKGROUND TASK STARTED for collection: '{collection_name}' with {len(filenames)} files. ---")
    
    successful_files = 0
    failed_files = 0
    
    for i, filename in enumerate(filenames, 1):
        file_path = os.path.join(TEMP_UPLOAD_DIR, filename)
        if not os.path.exists(file_path):
            print(f"!!! [background] File not found, skipping: {filename}")
            failed_files += 1
            continue
        
        print(f"[background] Processing file {i}/{len(filenames)}: {filename}")
        
        try:
            # Use the correct function name from influx_client
            await influx_client.ingest_wav_data_async(file_path, collection_name)
            successful_files += 1
            print(f"✅ [background] Successfully processed {filename}")
            
        except Exception as e:
            print(f"❌ [background] Failed to process {filename}: {e}")
            failed_files += 1
        
        finally:
            # Clean up the uploaded file
            try:
                os.remove(file_path)
            except:
                pass
    
    print(f"--- FAST BACKGROUND TASK FINISHED ---")
    print(f"    ✅ Successful: {successful_files}")
    print(f"    ❌ Failed: {failed_files}")
    print(f"    📊 Total: {len(filenames)}")

# --- UPDATED: Use optimized ingest endpoint ---
@router_audio.post("/api/audio/ingest", status_code=status.HTTP_202_ACCEPTED)
async def ingest_audio_files_optimized(
    background_tasks: BackgroundTasks,
    collection_name: str = Form(...),
    filenames: List[str] = Form(...)
):
    """
    Optimized audio ingestion with batching, downsampling, and progress tracking.
    """
    # Add the optimized long-running job to the background tasks queue
    background_tasks.add_task(process_and_ingest_files, collection_name, filenames)
    
    # Return immediate response
    return {
        "message": f"Accepted. FULL QUALITY ingestion for {len(filenames)} files into '{collection_name}' has started.",
        "optimization": "Using batched writes and vectorized operations - ALL samples preserved for audio playback.",
        "estimated_time": f"~{len(filenames) * 60} seconds for large files (storing every sample)"
    }

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
    return influx_client.get_collections()

@router_audio.get("/api/audio/waveform")
async def get_waveform_data(collection: str, start: str, end: str, points: int = 2000):
    return influx_client.query_waveform_data(collection, start, end, points)

# ... existing event endpoints unchanged ...
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
# backend/main.py (add this route to the router_audio section)

@router_audio.get("/api/audio/collections/{collection_name}/info")
async def get_collection_info(collection_name: str):
    """
    Gets metadata about a collection, including its total time range.
    """
    time_range = influx_client.get_collection_time_range(collection_name)
    if not time_range:
        raise HTTPException(
            status_code=404, 
            detail=f"No data or time range found for collection '{collection_name}'."
        )
    return {"time_range": time_range}

@router_audio.get("/api/audio/raw")
async def get_raw_audio_clip(collection: str, start: str, end: str):
    """
    Fetches raw audio samples, converts them to a WAV file in memory, and streams it.
    """
    # IMPORTANT: Adjust this to your actual sample rate if it's different.
    SAMPLE_RATE = 48000 

    # 1. Get the raw samples as a NumPy array
    np_samples = influx_client.query_raw_audio_data(collection, start, end)

    if np_samples.size == 0:
        raise HTTPException(status_code=404, detail="No audio data found for the requested range.")

    # 2. Use soundfile to write the NumPy array to an in-memory buffer
    buffer = io.BytesIO()
    sf.write(buffer, np_samples, samplerate=SAMPLE_RATE, format='WAV', subtype='PCM_16')
    buffer.seek(0)

    # 3. Stream the in-memory WAV file back to the client
    return StreamingResponse(buffer, media_type="audio/wav")

# Include all routers
app.include_router(router_status)
app.include_router(router_config)
app.include_router(router_events)
app.include_router(router_audio)