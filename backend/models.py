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

class Event(EventPayload):
    id: str

class VehicleConfig(BaseModel):
    id: str
    displayName: str
    category: str

# backend/models.py