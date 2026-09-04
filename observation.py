"""Schemas Pydantic para Observation."""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ObservationCreate(BaseModel):
    # Se omitido, o service usa datetime.now(timezone.utc) — ver crud/observation.py
    observed_at: Optional[datetime] = None
    notes: Optional[str] = None
    environmental_reading_id: Optional[uuid.UUID] = None


class ObservationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    culture_id: uuid.UUID
    observed_at: datetime
    relative_hours: Optional[float] = None
    notes: Optional[str] = None
    environmental_reading_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime
