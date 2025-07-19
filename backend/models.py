# backend/models.py
# --- FIX: Added 'Field' to the import statement ---
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class EventPayload(BaseModel):
    start_timestamp: datetime
    end_timestamp: datetime
    vehicle_type: str
    vehicle_identifier: Optional[str] = None
    direction: Optional[str] = None
    annotator_notes: Optional[str] = None
    status: Optional[str] = 'manual'

class Event(EventPayload):
    id: str

class VehicleConfig(BaseModel):
    id: str
    displayName: str
    category: str

class EventStatusUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(manual|refined|reviewed)$")

# backend/models.py