"""Schemas Pydantic para o CRUD de Experiment."""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.experiment import ExperimentStatus


class ExperimentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    hypothesis: Optional[str] = None


class ExperimentUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    hypothesis: Optional[str] = None
    status: Optional[ExperimentStatus] = None
    started_at: Optional[datetime] = None


class ExperimentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: Optional[str] = None
    hypothesis: Optional[str] = None
    status: ExperimentStatus
    started_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
