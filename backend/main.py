# backend/main.py
import uuid
import json
import os
import asyncio
import traceback
from datetime import datetime
from typing import List
from pathlib import Path
from multiprocessing import Pool, cpu_count

from fastapi import (
    FastAPI, HTTPException, Response, APIRouter, File, UploadFile, Form, BackgroundTasks, status
)
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

# Use relative imports now that 'backend' is a package
from .models import Event, EventPayload, VehicleConfig
from . import database as sqlite_db
from . import questdb_client

BACKEND_ROOT = Path(__file__).resolve().parent
SERVER_INGEST_DIR = (BACKEND_ROOT.parent / "data_to_ingest").resolve()

app = FastAPI(title="Audio Annotation API with QuestDB")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
async def startup_event():
    """Initializes databases and creates necessary directories on startup."""
    sqlite_db.init_db()
    os.makedirs(SERVER_INGEST_DIR, exist_ok=True)

# API Routers
router_status = APIRouter(tags=["Status"])
router_config = APIRouter(tags=["Configuration"])
router_events = APIRouter(tags=["Events - SQLite"])
router_audio = APIRouter(tags=["Audio - QuestDB"])

def run_ingestion_for_file(filepath: str, collection_name: str):
    """
    Synchronous helper function that encapsulates the CPU-heavy multiprocessing work.
    This function is designed to be called by `run_in_executor`.
    """
    print(f"  [Orchestrator] Preparing tasks for {os.path.basename(filepath)}...")
    tasks_to_run = questdb_client.prepare_ingestion_tasks(filepath, collection_name)
    
    num_processes = max(1, cpu_count() - 1)
    print(f"  [Orchestrator] Starting Pool with {num_processes} processes to handle {len(tasks_to_run)} chunks...")
    
    start_time = time.time()
    with Pool(processes=num_processes) as pool:
        pool.map(questdb_client.ingest_worker, tasks_to_run)
    end_time = time.time()
    
    duration = end_time - start_time
    print(f"  [Orchestrator] Finished processing in {duration:.2f} seconds.")

async def process_and_ingest_files(collection_name: str, filenames_to_ingest: List[str]):
    """
    Async background task that offloads the blocking multiprocessing work to a thread pool.
    """
    print(f"--- Background Task Started for collection: '{collection_name}' ---")
    loop = asyncio.get_running_loop()

    for filename in filenames_to_ingest:
        file_path = (SERVER_INGEST_DIR / filename).resolve()
        if not file_path.is_file():
            print(f"!!! [background] File '{filename}' not found in '{SERVER_INGEST_DIR}', skipping.")
            continue
        
        print(f"[background] Submitting ingestion for file: {file_path.name}")
        try:
            await loop.run_in_executor(
                None,  # Use the default thread pool executor
                run_ingestion_for_file,
                str(file_path),
                collection_name
            )
            print(f"Successfully submitted task for {filename}")
        except Exception:
            print(f"Failed to submit task for {filename}. Full traceback:")
            traceback.print_exc()
    print(f"--- Background Task Finished ---")

@router_audio.post("/api/audio/ingest", status_code=status.HTTP_202_ACCEPTED)
async def ingest_audio_files(
    background_tasks: BackgroundTasks,
    collection_name: str = Form(...),
    filenames: List[str] = Form(...)
):
    """Accepts ingestion request and starts the job in a true background task."""
    background_tasks.add_task(
        asyncio.create_task,
        process_and_ingest_files(collection_name, filenames)
    )
    return {"message": f"Ingestion kicked off for {len(filenames)} files.", "collection": collection_name}

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
    MAX_AUDIO_DURATION_SECONDS = 300
    try:
        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
        duration_seconds = (end_dt - start_dt).total_seconds()
        if duration_seconds > MAX_AUDIO_DURATION_SECONDS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Requested audio duration exceeds the limit of {MAX_AUDIO_DURATION_SECONDS}s.")
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

@router_config.get("/api/config/vehicles", response_model=List[VehicleConfig])
async def get_vehicle_config():
    try:
        with open(BACKEND_ROOT / "vehicles.json", "r") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error with vehicles.json: {e}")

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

app.include_router(router_status)
app.include_router(router_config)
app.include_router(router_events)
app.include_router(router_audio)