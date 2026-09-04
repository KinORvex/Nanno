"""Schemas Pydantic (DTOs) para o endpoint de previsão de tendência populacional."""
import uuid
from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field


class TrendForecastRequest(BaseModel):
    forecast_horizon_days: Optional[int] = Field(
        default=None,
        ge=1,
        le=30,
        description="Nº de dias a prever. Se omitido, usa o horizonte com que o modelo foi treinado.",
    )
    persist_as_trend_estimate: bool = Field(
        default=True,
        description="Se True, salva o resultado como um registro em TrendEstimate.",
    )


class TrendForecastResponse(BaseModel):
    project_id: uuid.UUID
    generated_at_date: date
    input_window_days: int
    forecast_horizon_days: int
    history_points_used: int

    predicted_density_cells_per_ml: List[float]
    lower_bound_cells_per_ml: List[float]
    upper_bound_cells_per_ml: List[float]
    trend_direction: str
    percent_change: float

    model_config = {"protected_namespaces": ()}  # evita conflito do pydantic com o prefixo "model_"
