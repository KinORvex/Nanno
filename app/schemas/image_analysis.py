"""Schema Pydantic de leitura de ImageAnalysis."""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.image import ProcessingStatus


class ImageAnalysisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    image_id: uuid.UUID
    observation_id: Optional[uuid.UUID] = None
    status: ProcessingStatus
    processing_error: Optional[str] = None
    algorithm_name: str
    algorithm_version: str
    preprocessing_version: Optional[str] = None
    segmentation_version: Optional[str] = None
    parameters: Optional[dict] = None
    metrics: Optional[dict] = None
    created_at: datetime
    updated_at: datetime
