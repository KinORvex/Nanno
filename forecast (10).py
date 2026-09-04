"""
Endpoint de previsao de tendencia populacional (calculo explicito, sob
demanda): usa o modelo LSTM treinado (app.ml) para projetar a densidade
celular futura de um projeto e persiste o resultado como um novo
TrendEstimate.

Para ler estimativas ja calculadas (sem forcar um novo calculo), veja
GET /trends/{project_id} em endpoints/trends.py -- ambos compartilham a
mesma logica de negocio em app.services.forecast_service.
"""
import logging
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_current_user
from app.core.database import get_db
from app.ml.dataset import InsufficientDataError
from app.ml.inference import ModelNotTrainedError
from app.models.project import AnalysisProject
from app.models.user import User
from app.schemas.forecast import TrendForecastRequest, TrendForecastResponse
from app.services.forecast_service import ForecastHorizonError, generate_trend_forecast

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects/{project_id}/forecast", tags=["forecast"])


def _get_owned_project(db: Session, project_id: uuid.UUID, user: User) -> AnalysisProject:
    project = db.get(AnalysisProject, project_id)
    if project is None or project.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Projeto nao encontrado.")
    return project


@router.post(
    "",
    response_model=TrendForecastResponse,
    summary="Forca o calculo de uma nova previsao de tendencia populacional",
)
async def create_trend_forecast(
    project_id: uuid.UUID,
    request: TrendForecastRequest = TrendForecastRequest(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TrendForecastResponse:
    project = _get_owned_project(db, project_id, current_user)

    try:
        result = await run_in_threadpool(
            generate_trend_forecast,
            db,
            project,
            request.forecast_horizon_days,
            request.persist_as_trend_estimate,
        )
    except InsufficientDataError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Historico insuficiente para gerar a previsao: {exc}",
        ) from exc
    except ModelNotTrainedError as exc:
        logger.error("Tentativa de previsao sem modelo treinado: %s", exc)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="O modelo de previsao ainda nao foi treinado neste ambiente.",
        ) from exc
    except ForecastHorizonError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return TrendForecastResponse(
        project_id=project.id,
        generated_at_date=date.today(),
        input_window_days=result.input_window_days,
        forecast_horizon_days=result.forecast_horizon_days,
        history_points_used=result.history_points_used,
        predicted_density_cells_per_ml=result.predicted_density_cells_per_ml,
        lower_bound_cells_per_ml=result.lower_bound_cells_per_ml,
        upper_bound_cells_per_ml=result.upper_bound_cells_per_ml,
        trend_direction=result.trend_direction,
        percent_change=result.percent_change,
    )
