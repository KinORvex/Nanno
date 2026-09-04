"""Schemas Pydantic para o endpoint GET /trends/{project_id}."""
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from app.models.trend import TrendDirection, TrendMetric


class TrendEstimateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    metric: TrendMetric
    direction: TrendDirection
    period_start: datetime
    period_end: datetime
    value_start: Optional[float] = None
    value_end: Optional[float] = None
    percent_change: Optional[float] = None
    method: str
    created_at: datetime


class TrendEstimatesResponse(BaseModel):
    project_id: uuid.UUID
    estimates: List[TrendEstimateRead]
    generated_fresh: bool  # True se uma nova previsão foi calculada nesta chamada
