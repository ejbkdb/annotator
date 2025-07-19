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
from .models import Event, EventPayload, VehicleConfig, EventStatusUpdate 
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
    if not event_dict:
        raise HTTPException(status_code=404, detail="Event not found.")
    
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

@router_export.get("/api/export/dataset")
async def export_dataset(start_date: Optional[str] = None, end_date: Optional[str] = None, vehicle_types: Optional[List[str]] = Query(None)):
    """
    Export refined events as an ML-ready dataset in JSON format.
    Filters by date and vehicle types.
    """
    refined_events = database.get_all_events_from_db(status='refined')
    
    filtered_events = []
    for event in refined_events:
        event_start = datetime.fromisoformat(event['start_timestamp'])
        
        if start_date and event_start < datetime.fromisoformat(start_date):
            continue
        if end_date and event_start > datetime.fromisoformat(end_date):
            continue
        if vehicle_types and event['vehicle_type'] not in vehicle_types:
            continue
        filtered_events.append(event)

    annotations = []
    category_stats = {}
    for event in filtered_events:
        start_ts = datetime.fromisoformat(event['start_timestamp'])
        end_ts = datetime.fromisoformat(event['end_timestamp'])
        duration = (end_ts - start_ts).total_seconds()
        annotations.append({
            "id": event['id'], "vehicle_type": event['vehicle_type'],
            "start_timestamp": event['start_timestamp'], "end_timestamp": event['end_timestamp'],
            "duration_seconds": round(duration, 3), "vehicle_identifier": event.get('vehicle_identifier'),
            "direction": event.get('direction'), "notes": event.get('annotator_notes')
        })
        cat = event['vehicle_type']
        if cat not in category_stats:
            category_stats[cat] = {"count": 0, "total_duration": 0}
        category_stats[cat]["count"] += 1
        category_stats[cat]["total_duration"] += duration

    for cat, data in category_stats.items():
        avg_duration = data['total_duration'] / data['count'] if data['count'] > 0 else 0
        category_stats[cat]['avg_duration'] = round(avg_duration, 3)

    dataset_metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(), "total_events": len(annotations),
        "date_range": {"start": start_date, "end": end_date}, "categories": list(category_stats.keys())
    }
    final_export = {
        "dataset_metadata": dataset_metadata, "annotations": annotations, "category_stats": category_stats
    }
    return JSONResponse(content=final_export)

app.include_router(router_status)
app.include_router(router_config)
app.include_router(router_events)
app.include_router(router_audio)
app.include_router(router_export)