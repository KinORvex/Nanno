"""Schema Pydantic de leitura de Prediction."""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.trend import TrendMetric


class PredictionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    culture_id: uuid.UUID
    target_timestamp: datetime
    metric: TrendMetric
    predicted_value: float
    confidence: Optional[float] = None
    model_name: str
    model_version: str
    created_at: datetime
