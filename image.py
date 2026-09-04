"""Schemas Pydantic (DTOs) para o recurso de imagens."""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.image import ProcessingStatus


class MicroalgaeImageBase(BaseModel):
    original_filename: str
    content_type: str
    file_size_bytes: int
    width_px: Optional[int] = None
    height_px: Optional[int] = None
    captured_at: Optional[datetime] = None


class MicroalgaeImageCreate(MicroalgaeImageBase):
    project_id: uuid.UUID


class MicroalgaeImageMetricsUpdate(BaseModel):
    """Payload enviado pelo pipeline de visão computacional após processar a imagem."""

    cell_count: int
    avg_cell_diameter_um: float
    std_cell_diameter_um: Optional[float] = None
    cell_density_cells_per_ml: Optional[float] = None
    confidence_score: Optional[float] = None
    extra_metrics: Optional[dict] = None


class MicroalgaeImageRead(MicroalgaeImageBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    s3_bucket: str
    s3_key: str
    processing_status: ProcessingStatus
    processing_error: Optional[str] = None
    cell_count: Optional[int] = None
    avg_cell_diameter_um: Optional[float] = None
    std_cell_diameter_um: Optional[float] = None
    cell_density_cells_per_ml: Optional[float] = None
    confidence_score: Optional[float] = None
    created_at: datetime
    updated_at: datetime


class MicroalgaeImageDownloadURL(BaseModel):
    url: str
    expires_in: int
