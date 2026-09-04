"""
Núcleo de negócio da previsão de tendência populacional — extraído para cá
para ser reutilizado tanto pelo `POST /projects/{project_id}/forecast`
(força um novo cálculo) quanto pelo `GET /trends/{project_id}` (calcula sob
demanda apenas se não houver uma estimativa recente persistida).

Framework-agnostic: não importa FastAPI nem levanta HTTPException — os
endpoints traduzem as exceções deste módulo para respostas HTTP.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from app.ml.dataset import InsufficientDataError, build_feature_matrix
from app.ml.inference import ForecastModelRegistry, ModelNotTrainedError
from app.models.project import AnalysisProject
from app.models.trend import TrendDirection, TrendEstimate, TrendMetric
from app.services.forecast_data import get_daily_time_series

__all__ = [
    "TrendForecastResult",
    "ForecastHorizonError",
    "generate_trend_forecast",
    "get_recent_trend_estimates",
]

_DIRECTION_MAP = {
    "increasing": TrendDirection.INCREASING,
    "decreasing": TrendDirection.DECREASING,
    "stable": TrendDirection.STABLE,
}


class ForecastHorizonError(Exception):
    """O horizonte de previsão solicitado excede o horizonte com que o modelo foi treinado."""


@dataclass
class TrendForecastResult:
    predicted_density_cells_per_ml: List[float]
    lower_bound_cells_per_ml: List[float]
    upper_bound_cells_per_ml: List[float]
    trend_direction: str
    percent_change: float
    input_window_days: int
    forecast_horizon_days: int
    history_points_used: int
    trend_estimate_id: Optional[uuid.UUID] = None


def _classify_trend(
    predicted: List[float], records: List[dict], stability_threshold_pct: float = 5.0
) -> tuple[str, float]:
    """Classifica a direção da tendência com base no último ponto previsto
    versus a observação real mais recente disponível na série."""
    if not predicted:
        return "stable", 0.0

    current = next(
        (r["cell_density_cells_per_ml"] for r in reversed(records) if r.get("cell_density_cells_per_ml")),
        None,
    )
    if not current:
        return "stable", 0.0

    percent_change = ((predicted[-1] - current) / current) * 100.0
    if abs(percent_change) < stability_threshold_pct:
        return "stable", percent_change
    return ("increasing" if percent_change > 0 else "decreasing"), percent_change


def generate_trend_forecast(
    db: Session,
    project: AnalysisProject,
    forecast_horizon_days: Optional[int] = None,
    persist: bool = True,
) -> TrendForecastResult:
    """
    Executa o pipeline completo: monta a série temporal do projeto, roda o
    modelo LSTM treinado (com MC-Dropout para incerteza) e opcionalmente
    persiste o resultado como um novo `TrendEstimate`.

    Raises:
        InsufficientDataError: histórico do projeto é curto demais.
        ModelNotTrainedError: nenhum checkpoint treinado disponível.
        ForecastHorizonError: horizonte solicitado maior que o treinado.
    """
    records = get_daily_time_series(db, project.id)
    feature_matrix = build_feature_matrix(records)  # levanta InsufficientDataError

    registry = ForecastModelRegistry.get_instance()
    forecast = registry.predict(feature_matrix)  # levanta ModelNotTrainedError
    config = registry.config

    trained_horizon = config.forecast_horizon
    requested_horizon = forecast_horizon_days or trained_horizon
    if requested_horizon > trained_horizon:
        raise ForecastHorizonError(
            f"O modelo atual foi treinado para prever no máximo {trained_horizon} dias "
            f"(solicitado: {requested_horizon})."
        )

    predicted = forecast.predicted_density[:requested_horizon]
    lower = forecast.lower_bound[:requested_horizon]
    upper = forecast.upper_bound[:requested_horizon]
    direction, percent_change = _classify_trend(predicted, records)

    trend_estimate_id = None
    if persist:
        now = datetime.now(timezone.utc)
        trend = TrendEstimate(
            project_id=project.id,
            metric=TrendMetric.CELL_DENSITY,
            direction=_DIRECTION_MAP[direction],
            period_start=now,
            period_end=now + timedelta(days=requested_horizon),
            value_start=predicted[0] if predicted else None,
            value_end=predicted[-1] if predicted else None,
            percent_change=percent_change,
            method="lstm_forecaster_v1",
        )
        db.add(trend)
        db.commit()
        db.refresh(trend)
        trend_estimate_id = trend.id

    return TrendForecastResult(
        predicted_density_cells_per_ml=predicted,
        lower_bound_cells_per_ml=lower,
        upper_bound_cells_per_ml=upper,
        trend_direction=direction,
        percent_change=percent_change,
        input_window_days=config.input_window,
        forecast_horizon_days=requested_horizon,
        history_points_used=len(records),
        trend_estimate_id=trend_estimate_id,
    )


def get_recent_trend_estimates(
    db: Session, project_id: uuid.UUID, metric: TrendMetric = TrendMetric.CELL_DENSITY, limit: int = 10
) -> List[TrendEstimate]:
    """Retorna as estimativas de tendência já persistidas, mais recentes primeiro."""
    return (
        db.query(TrendEstimate)
        .filter(TrendEstimate.project_id == project_id, TrendEstimate.metric == metric)
        .order_by(TrendEstimate.created_at.desc())
        .limit(limit)
        .all()
    )
