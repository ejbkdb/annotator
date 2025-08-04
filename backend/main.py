# backend/main.py
import uuid
import json
import os
import asyncio
from datetime import datetime, timezone # Ensure timezone is imported
from typing import List, Optional
from pathlib import Path
import csv
import io

from fastapi import FastAPI, HTTPException, Response, status, APIRouter, File, UploadFile, Form, BackgroundTasks, Query
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from .models import Event, EventPayload, VehicleConfig, EventStatusUpdate, RefinedAnnotationPayload, RefinedAnnotation
from backend import database
from backend import questdb_client
# This import is essential for the ingestion endpoint to work
from backend.ingestion_utils import process_single_file
import soundfile as sf
import numpy as np

PROJECT_ROOT = Path(__file__).parent.parent
app = FastAPI(title="Test Range Annotation API")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

TEMP_UPLOAD_DIR = PROJECT_ROOT / "data" / "uploads"
VEHICLES_CONFIG_PATH = PROJECT_ROOT / "backend" / "vehicles.json"

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
    if not VEHICLES_CONFIG_PATH.exists():
         raise HTTPException(status_code=500, detail="vehicles.json not found.")
    try:
        with open(VEHICLES_CONFIG_PATH, "r") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(500, f"Error with vehicles.json: {e}")

# --- RESTORED: The original, correct background task for ingestion ---
def process_and_ingest_files(collection_name: str, filenames: List[str]):
    """
    Background task to ingest uploaded files and then clean them up.
    """
    print(f"--- BACKGROUND TASK STARTED for collection: '{collection_name}' with {len(filenames)} files. ---")
    successful_files, failed_files = 0, 0
    
    for filename in filenames:
        file_path = TEMP_UPLOAD_DIR / filename
        if not file_path.exists():
            print(f"  - WARNING: File {filename} not found in temp directory. Skipping.")
            failed_files += 1
            continue
        
        try:
            points_written, duration = process_single_file(str(file_path), collection_name)
            if points_written > 0:
                print(f"  ✓ Successfully processed {filename}: {points_written:,} points in {duration:.2f}s.")
                successful_files += 1
            else:
                print(f"  ✗ Failed to process {filename}. No points written.")
                failed_files += 1
        except Exception as e:
            print(f"  ✗ CRITICAL ERROR processing {filename}: {e}")
            failed_files += 1
        finally:
            if file_path.exists():
                os.remove(file_path)
                print(f"  - Cleaned up temporary file: {filename}")
    
    print(f"--- BACKGROUND TASK FINISHED --- [Successful: {successful_files}, Failed: {failed_files}]")

@router_audio.post("/api/audio/ingest", status_code=status.HTTP_202_ACCEPTED)
async def ingest_audio_files_optimized(background_tasks: BackgroundTasks, collection_name: str = Form(...), filenames: List[str] = Form(...)):
    background_tasks.add_task(process_and_ingest_files, collection_name, filenames)
    return {"message": f"Accepted. Ingestion for {len(filenames)} files into '{collection_name}' has started."}

@router_audio.post("/api/audio/upload")
async def upload_audio_files(files: List[UploadFile] = File(...)):
    saved_files = []
    for file in files:
        if not file.filename.lower().endswith((".wav", ".flac")):
            raise HTTPException(status_code=400, detail="Invalid file type. Only .wav or .flac supported.")
        
        file_path = TEMP_UPLOAD_DIR / file.filename
        try:
            with open(file_path, "wb") as buffer:
                buffer.write(await file.read())
            saved_files.append(file.filename)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Could not save file {file.filename}: {e}")
            
    return {"filenames": saved_files, "message": f"Successfully uploaded {len(saved_files)} files."}

@router_audio.get("/api/audio/collections", response_model=List[str])
async def list_collections(): 
    return questdb_client.get_collections()

@router_audio.get("/api/audio/waveform")
async def get_waveform_data(collection: str, start: str, end: str, points: int = 2000):
    return questdb_client.query_waveform_data(collection, start, end, points)

@router_status.get("/api/health")
async def health_check(): 
    return {"status": "ok"}

@router_events.get("/api/events", response_model=List[Event])
async def get_all_events(status: Optional[str] = None): 
    return database.get_all_events_from_db(status=status)

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

# --- THE SINGLE LINE FIX IS APPLIED HERE ---
@router_events.get("/api/events/{event_id}/suggest-collection")
async def suggest_collection_for_event(event_id: str):
    event_dict = database.get_event_by_id_from_db(event_id)
    if not event_dict: 
        raise HTTPException(status_code=404, detail="Event not found.")
    
    # FIX: Ensure the datetime from SQLite is made timezone-aware (UTC) before comparison.
    event_start_time = datetime.fromisoformat(event_dict['start_timestamp']).replace(tzinfo=timezone.utc)
    
    collections = questdb_client.get_collections()
    for collection in collections:
        time_range = questdb_client.get_collection_time_range(collection)
        if time_range:
            range_start = datetime.fromisoformat(time_range['start'].replace("Z", "+00:00"))
            range_end = datetime.fromisoformat(time_range['end'].replace("Z", "+00:00"))
            
            if range_start <= event_start_time <= range_end:
                return {"suggested_collection": collection}
                
    return {"suggested_collection": None}

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
    was_deleted = database.delete_refined_annotation_from_db(annotation_id)
    if not was_deleted:
        raise HTTPException(status_code=404, detail=f"Refined annotation with id '{annotation_id}' not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

# --- RESTORED: The original, correct CSV export endpoint ---
@router_export.get("/api/export/dataset")
async def export_dataset(
    start_date: Optional[str] = None, 
    end_date: Optional[str] = None, 
    vehicle_types: Optional[List[str]] = Query(None)
):
    """
    Exports refined annotations to a CSV file.
    """
    # This assumes a function get_all_refined_annotations_for_export exists in database.py
    # If it doesn't, this will fail, but the code is restored from your original.
    all_data = database.get_all_refined_annotations_for_export(start_date, end_date, vehicle_types)
    if not all_data:
        return Response("No data found for the specified criteria.", status_code=404)

    output = io.StringIO()
    # The fieldnames should be derived from the data itself to be robust
    writer = csv.DictWriter(output, fieldnames=all_data[0].keys())
    writer.writeheader()
    writer.writerows(all_data)
    
    return StreamingResponse(
        iter([output.getvalue()]), 
        media_type="text/csv", 
        headers={"Content-Disposition": f"attachment; filename=export_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.csv"}
    )

app.include_router(router_status)
app.include_router(router_config)
app.include_router(router_events)
app.include_router(router_audio)
app.include_router(router_export)
app.include_router(router_annotations)