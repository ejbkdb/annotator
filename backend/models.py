# backend/models.py
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class EventPayload(BaseModel):
    start_timestamp: datetime
    end_timestamp: datetime
    vehicle_type: str
    vehicle_identifier: Optional[str] = None
    direction: Optional[str] = None
    annotator_notes: Optional[str] = None
    convoy_id: Optional[str] = None
    vehicle_action: Optional[str] = 'driveby'

class Event(EventPayload):
    id: str

class VehicleConfig(BaseModel):
    id: str
    displayName: str
    category: str

# --- REFACTORED CONVOY MODELS ---

class ConvoyCreationPayload(BaseModel):
    """Payload to create a new convoy record."""
    convoy_number: str
    direction: str
    notes: Optional[str] = None
    convoy_spacing_seconds: Optional[int] = None

class ConvoyUpdatePayload(BaseModel):
    """Payload to update an existing convoy's metadata."""
    direction: Optional[str] = None
    notes: Optional[str] = None
    convoy_spacing_seconds: Optional[int] = None

class Convoy(BaseModel):
    """Represents a full convoy object, used for DB and API responses."""
    id: str
    convoy_number: str
    direction: str
    notes: Optional[str] = None
    convoy_spacing_seconds: Optional[int] = None
    created_at: datetime