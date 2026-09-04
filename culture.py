"""Schemas Pydantic para Culture, incluindo série temporal e comparação."""
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class CultureCreate(BaseModel):
    label: str = Field(min_length=1, max_length=50)
    condition_label: str = Field(min_length=1, max_length=120)
    description: Optional[str] = None
    started_at: Optional[datetime] = None


class CultureUpdate(BaseModel):
    description: Optional[str] = None
    started_at: Optional[datetime] = None
    stress_induced_at: Optional[datetime] = None


class CultureRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    experiment_id: uuid.UUID
    label: str
    condition_label: str
    description: Optional[str] = None
    started_at: Optional[datetime] = None
    stress_induced_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class EnvironmentalSnapshot(BaseModel):
    """Achatamento leve de EnvironmentalReading para uso dentro do histórico
    de uma cultura (evita reexpor o model inteiro com campos irrelevantes aqui)."""

    model_config = ConfigDict(from_attributes=True)

    temperature_c: Optional[float] = None
    ph: Optional[float] = None
    salinity_psu: Optional[float] = None
    light_intensity_umol_m2_s: Optional[float] = None
    dissolved_oxygen_mg_l: Optional[float] = None


class CultureHistoryPoint(BaseModel):
    observation_id: uuid.UUID
    observed_at: datetime
    relative_hours: Optional[float] = None
    metrics: Optional[dict] = None
    environmental_conditions: Optional[EnvironmentalSnapshot] = None
    health_state: Optional[str] = None


class CultureHistoryResponse(BaseModel):
    culture_id: uuid.UUID
    label: str
    condition_label: str
    points: List[CultureHistoryPoint]


class CultureComparisonResponse(BaseModel):
    cultures: List[CultureHistoryResponse]
