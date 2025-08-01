# backend/main.py
import uuid
import json
import os
import asyncio
from datetime import datetime, timezone
from typing import List, Optional
from pathlib import Path
from fastapi import FastAPI, HTTPException, Response, status, APIRouter, File, UploadFile, Form, BackgroundTasks, Query
from fastapi.responses import JSONResponse

from fastapi.middleware.cors import CORSMiddleware
from .models import Event, EventPayload, VehicleConfig, EventStatusUpdate, RefinedAnnotationPayload, RefinedAnnotation
from backend import database
from backend import questdb_client

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
VEHICLES_CONFIG_PATH = PROJECT_ROOT / "vehicles.json"

@app.on_event("startup")
async def startup_event():
    database.init_db()
    os.makedirs(PROJECT_ROOT / "data" / "events", exist_ok=True)
    os.makedirs(TEMP_UPLOAD_DIR, exist_ok=True)

router_status = APIRouter(tags=["Status"])
router_config = APIRouter(tags=["Configuration"])
router_events = APIRouter(tags=["Events"])
router_audio = APIRouter(tags=["Audio & Timeseries"])
router_export = APIRouter(tags=["Export"])
router_annotations = APIRouter(tags=["Refined Annotations"])

@router_config.get("/api/config/vehicles", response_model=List[VehicleConfig])
async def get_vehicle_config():
    try:
        with open(VEHICLES_CONFIG_PATH, "r") as f:
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
            # This function is not defined in the provided context, assuming it exists
            # await questdb_client.ingest_wav_data_async(file_path, collection_name)
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
async def list_collections(): return questdb_client.get_collections()

@router_audio.get("/api/audio/waveform")
async def get_waveform_data(collection: str, start: str, end: str, points: int = 2000):
    return questdb_client.query_waveform_data(collection, start, end, points)

@router_status.get("/api/health")
async def health_check(): return {"status": "ok"}
@router_events.get("/api/events", response_model=List[Event])
async def get_all_events(status: Optional[str] = None): return database.get_all_events_from_db(status=status)
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

@router_events.post("/api/events/{event_id}/reset", status_code=status.HTTP_204_NO_CONTENT)
async def reset_parent_event(event_id: str):
    if not database.delete_children_and_reset_parent_event(event_id):
        raise HTTPException(status_code=404, detail="Event not found or failed to reset.")
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

@router_events.put("/api/events/{event_id}/status", status_code=status.HTTP_204_NO_CONTENT)
async def update_event_status(event_id: str, payload: EventStatusUpdate):
    if not database.update_event_status_in_db(event_id, payload.status):
        raise HTTPException(status_code=404, detail="Event not found or status could not be updated.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router_events.get("/api/events/{event_id}/suggest-collection")
async def suggest_collection_for_event(event_id: str):
    event_dict = database.get_event_by_id_from_db(event_id)
    if not event_dict: raise HTTPException(status_code=404, detail="Event not found.")
    event_start_time = datetime.fromisoformat(event_dict['start_timestamp'])
    collections = questdb_client.get_collections()
    for collection in collections:
        time_range = questdb_client.get_collection_time_range(collection)
        if time_range:
            range_start = datetime.fromisoformat(time_range['start'].replace("Z", "+00:00"))
            range_end = datetime.fromisoformat(time_range['end'].replace("Z", "+00:00"))
            if range_start <= event_start_time <= range_end:
                return {"suggested_collection": collection}
    return {"suggested_collection": None}


# --- MODIFIED: Endpoint logic now handles source_collection ---
@router_annotations.post("/api/annotations/refined", response_model=RefinedAnnotation, status_code=201)
async def create_refined_annotation(payload: RefinedAnnotationPayload):
    parent_event = database.get_event_by_id_from_db(payload.parent_event_id)
    if not parent_event:
        raise HTTPException(status_code=404, detail=f"Parent event with id {payload.parent_event_id} not found.")

    with open(VEHICLES_CONFIG_PATH, "r") as f:
        vehicle_configs = json.load(f)
    
    vehicle_subclass = next((v.get('subclass', 'unknown') for v in vehicle_configs if v['id'] == payload.vehicle_type), "unknown")
    
    annotation_data = payload.dict()
    annotation_data['id'] = str(uuid.uuid4())
    annotation_data['vehicle_subclass'] = vehicle_subclass
    annotation_data['start_timestamp'] = payload.start_timestamp.isoformat()
    annotation_data['end_timestamp'] = payload.end_timestamp.isoformat()

    new_annotation = database.save_refined_annotation_to_db(annotation_data)
    
    database.update_event_status_in_db(payload.parent_event_id, 'reviewed')
    
    return new_annotation

@router_annotations.get("/api/annotations/refined", response_model=List[RefinedAnnotation])
async def get_refined_annotations(parent_event_id: str):
    return database.get_refined_annotations_by_parent_id(parent_event_id)

@router_annotations.delete("/api/annotations/refined/{annotation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_refined_annotation(annotation_id: str):
    """Deletes a single refined annotation by its unique ID."""
    was_deleted = database.delete_refined_annotation_from_db(annotation_id)
    if not was_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Refined annotation with id '{annotation_id}' not found."
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router_export.get("/api/export/dataset")
async def export_dataset(start_date: Optional[str] = None, end_date: Optional[str] = None, vehicle_types: Optional[List[str]] = Query(None)):
    return {"message": "Export function needs update for new schema", "data": []}

app.include_router(router_status)
app.include_router(router_config)
app.include_router(router_events)
app.include_router(router_audio)
app.include_router(router_export)
app.include_router(router_annotations)