"""Schemas Pydantic para o CRUD de AnalysisProject."""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.project import ProjectStatus


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    species: str = Field(default="Nannochloropsis", max_length=120)


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[ProjectStatus] = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: Optional[str] = None
    species: str
    status: ProjectStatus
    owner_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ProjectSummary(ProjectRead):
    """Variante de ProjectRead com contadores agregados, usada na listagem."""

    image_count: int = 0
    latest_cell_count: Optional[int] = None
