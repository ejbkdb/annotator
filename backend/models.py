# backend/models.py
# Pydantic Models for API validation and serialization (Used by the Basic API in main.py).
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

# class EventPayload(BaseModel):
#     start_timestamp: datetime
#     end_timestamp: datetime
#     vehicle_type: str
#     vehicle_identifier: Optional[str] = None
#     direction: Optional[str] = None
#     annotator_notes: Optional[str] = None
#     status: Optional[str] = 'manual'

class EventPayload(BaseModel):
    start_timestamp: datetime
    end_timestamp: datetime
    vehicle_type: str
    vehicle_identifier: Optional[str] = None
    
    # --- ADDED/MODIFIED FIELDS ---
    location: Optional[str] = None  # Add the location field
    action: Optional[str] = None    # Add the action field
    direction: Optional[str] = None
    annotation: Optional[str] = None # Use 'annotation' to match the DB
    # --- END OF CHANGES ---

    status: Optional[str] = 'manual'

class Event(EventPayload):
    id: str

class VehicleConfig(BaseModel):
    id: str
    displayName: str
    category: str
    subclass: str

class EventStatusUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(manual|refined|reviewed)$")

class RefinedAnnotationPayload(BaseModel):
    parent_event_id: str
    source_collection: str
    start_timestamp: datetime
    end_timestamp: datetime
    vehicle_type: str
    location: str = Field(..., pattern=r"^(tarmac|fastpass|jungle)$")
    action: str = Field(..., pattern=r"^(driveby|rev|idle|flying|hover)$")
    direction: str = Field(..., pattern=r"^(towards_de|towards_103|na|clockwise|counter-clockwise)$")
    annotator_notes: Optional[str] = None

class RefinedAnnotation(RefinedAnnotationPayload):
    id: str
    vehicle_subclass: str
