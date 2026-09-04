"""Schemas Pydantic para o Gêmeo Digital (estado, histórico, avaliação de estresse)."""
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from app.models.digital_twin import HealthStatus


class DigitalTwinStateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    culture_id: uuid.UUID
    based_on_observation_id: Optional[uuid.UUID] = None
    computed_at: datetime
    biomass_estimate: Optional[float] = None
    density_estimate: Optional[float] = None
    morphological_state: Optional[dict] = None
    environmental_state: Optional[dict] = None
    growth_state: Optional[str] = None
    health_status: HealthStatus
    stress_score: Optional[float] = None
    confidence: Optional[float] = None
    contributing_factors: Optional[dict] = None
    created_at: datetime


class DigitalTwinHistoryResponse(BaseModel):
    culture_id: uuid.UUID
    states: List[DigitalTwinStateRead]


class StressAssessmentResponse(BaseModel):
    """Recorte do DigitalTwinState mais recente, focado especificamente em estresse."""

    culture_id: uuid.UUID
    computed_at: Optional[datetime] = None
    health_status: HealthStatus
    stress_score: Optional[float] = None
    confidence: Optional[float] = None
    contributing_factors: Optional[dict] = None
    message: Optional[str] = None  # ex.: motivo de UNKNOWN (dados insuficientes)
