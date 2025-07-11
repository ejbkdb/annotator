# backend/main.py
import uuid
import json
import os
import asyncio
import traceback
from datetime import datetime
from typing import List
from pathlib import Path

from fastapi import (
    FastAPI, HTTPException, Response, APIRouter, File, UploadFile, Form, BackgroundTasks, status
)
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from models import Event, EventPayload, VehicleConfig
import database as sqlite_db
import questdb_client
import io
import soundfile as sf
import numpy as np

# Use a more robust pathing strategy.
# This assumes main.py is in the /backend directory.
BACKEND_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_ROOT.parent

app = FastAPI(title="Audio Annotation API with QuestDB")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

SERVER_INGEST_DIR = Path("/home/eborcherding/Documents/florida/test").resolve()
os.makedirs(SERVER_INGEST_DIR, exist_ok=True) # Ensure the directory exists on startup

# Note: /tmp or a dedicated volume is better for production.
# For simplicity in this project structure, we'll keep it here.
TEMP_UPLOAD_DIR = BACKEND_ROOT / "data" / "uploads"

@app.on_event("startup")
async def startup_event():
    """Initializes databases and creates necessary directories on startup."""
    sqlite_db.init_db()
    os.makedirs(BACKEND_ROOT / "data" / "events", exist_ok=True)
    os.makedirs(TEMP_UPLOAD_DIR, exist_ok=True)

# API Routers
router_status = APIRouter(tags=["Status"])
router_config = APIRouter(tags=["Configuration"])
router_events = APIRouter(tags=["Events - SQLite"])
router_audio = APIRouter(tags=["Audio - QuestDB"])

@router_config.get("/api/config/vehicles", response_model=List[VehicleConfig])
async def get_vehicle_config():
    try:
        with open(BACKEND_ROOT / "vehicles.json", "r") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error with vehicles.json: {e}")

# async def process_and_ingest_files(collection_name: str, filenames: List[str]):
#     """Background task to process and ingest uploaded files into QuestDB."""
#     print(f"--- QuestDB Background Task Started for collection: '{collection_name}' with {len(filenames)} files. ---")
#     successful_files, failed_files = 0, 0
    
#     for i, filename in enumerate(filenames, 1):
#         file_path = TEMP_UPLOAD_DIR / filename
#         if not file_path.exists():
#             print(f"!!! [background] File not found, skipping: {filename}")
#             failed_files += 1
#             continue
        
#         print(f"[background] Processing file {i}/{len(filenames)}: {filename}")
        
#         try:
#             await questdb_client.ingest_wav_data_async(str(file_path), collection_name)
#             successful_files += 1
#             print(f"Successfully processed {filename}")
#         except Exception:
#             # Improve error logging to provide more context on failure.
#             print(f"Failed to process {filename}. Full traceback:")
#             traceback.print_exc()
#             failed_files += 1
#         finally:
#             # Use the idiomatic and safer Path.unlink() method.
#             if file_path.exists():
#                 file_path.unlink()
    
#     print(f"--- QuestDB Background Task Finished ---")
#     print(f"    Successful: {successful_files}")
#     print(f"    Failed: {failed_files}")
async def process_and_ingest_files(collection_name: str, filenames_to_ingest: List[str]):
    """
    Background task that finds and processes files from the predefined server directory.
    """
    print(f"--- QuestDB Background Task Started for collection: '{collection_name}' with {len(filenames_to_ingest)} files. ---")
    
    for filename in filenames_to_ingest:
        # Construct the full, absolute path by combining the hardcoded directory and the filename.
        file_path = (SERVER_INGEST_DIR / filename).resolve()
        
        if not file_path.exists() or not file_path.is_file():
            print(f"!!! [background] File '{filename}' not found in '{SERVER_INGEST_DIR}', skipping.")
            continue
        
        print(f"[background] Processing file: {file_path.name}")
        
        try:
            await questdb_client.ingest_wav_data_async(str(file_path), collection_name)
            print(f"Successfully processed {filename}")
        except Exception:
            print(f"Failed to process {filename}. Full traceback:")
            traceback.print_exc()
        # NOTE: We do not delete the source file in this workflow.
    
    print(f"--- QuestDB Background Task Finished ---")
@router_audio.post("/api/audio/ingest", status_code=status.HTTP_202_ACCEPTED)
async def ingest_audio_files(
    background_tasks: BackgroundTasks,
    collection_name: str = Form(...),
    filenames: List[str] = Form(...)
):
    """Accepts ingestion request and starts the job in a true background task."""
    # Wrap the async task in asyncio.create_task to run it truly in the background,
    # preventing the HTTP response from being blocked.
    background_tasks.add_task(
        asyncio.create_task,
        process_and_ingest_files(collection_name, filenames)
    )
    return {
        "message": f"Ingestion kicked off for {len(filenames)} files.",
        "collection": collection_name
    }

@router_audio.post("/api/audio/upload", response_model=dict)
async def upload_audio_files(files: List[UploadFile] = File(...)):
    """Uploads WAV files to a temporary directory for processing."""
    saved_files = []
    for file in files:
        if not file.filename.lower().endswith((".wav", ".wave")):
            raise HTTPException(status_code=400, detail="Invalid file type. Only .wav supported.")
        file_path = TEMP_UPLOAD_DIR / file.filename
        with open(file_path, "wb") as buffer:
            buffer.write(await file.read())
        saved_files.append(file.filename)
    return {"filenames": saved_files, "message": f"Successfully uploaded {len(saved_files)} files."}

@router_audio.get("/api/audio/collections", response_model=List[str])
async def list_collections():
    return questdb_client.get_collections()

@router_audio.get("/api/audio/waveform", response_model=List[dict])
async def get_waveform_data(collection: str, start: str, end: str, points: int = 2000):
    return questdb_client.query_waveform_data(collection, start, end, points)

@router_audio.get("/api/audio/collections/{collection_name}/info", response_model=dict)
async def get_collection_info(collection_name: str):
    time_range = questdb_client.get_collection_time_range(collection_name)
    if not time_range:
        raise HTTPException(status_code=404, detail=f"No data or time range found for collection '{collection_name}'.")
    return {"time_range": time_range}

@router_audio.get("/api/audio/raw")
async def get_raw_audio_clip(collection: str, start: str, end: str):
    """Fetches raw audio samples and streams them back as a WAV file."""
    # Add a max-duration guardrail to prevent OOM errors from huge requests.
    MAX_AUDIO_DURATION_SECONDS = 300  # 5 minutes
    try:
        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
        duration_seconds = (end_dt - start_dt).total_seconds()
        if duration_seconds > MAX_AUDIO_DURATION_SECONDS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Requested audio duration ({duration_seconds:.0f}s) exceeds the maximum limit of {MAX_AUDIO_DURATION_SECONDS}s."
            )
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid timestamp format.")

    SAMPLE_RATE = 48000
    np_samples = questdb_client.query_raw_audio_data(collection, start, end)

    if np_samples.size == 0:
        raise HTTPException(status_code=404, detail="No audio data found for the requested range.")

    buffer = io.BytesIO()
    sf.write(buffer, np_samples, samplerate=SAMPLE_RATE, format='WAV', subtype='PCM_16')
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="audio/wav")

# --- Event Endpoints (SQLite - No Changes) ---
@router_status.get("/api/health")
async def health_check(): return {"status": "ok"}

@router_events.get("/api/events", response_model=List[Event])
async def get_all_events(): return sqlite_db.get_all_events_from_db()

@router_events.post("/api/events", response_model=Event, status_code=status.HTTP_201_CREATED)
async def create_event(payload: EventPayload):
    event = Event(id=str(uuid.uuid4()), **payload.dict())
    sqlite_db.save_event_to_db(event)
    return event

@router_events.delete("/api/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(event_id: str):
    if not sqlite_db.delete_event_from_db(event_id):
        raise HTTPException(status_code=404, detail="Event not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

# Include all routers in the main FastAPI app
app.include_router(router_status)
app.include_router(router_config)
app.include_router(router_events)
app.include_router(router_audio)