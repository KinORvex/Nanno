"""
Endpoint de leitura das estimativas de tendência populacional.

Comportamento: se já existir uma estimativa persistida para o projeto,
retorna as mais recentes (leitura rápida, sem reexecutar o modelo). Se não
houver nenhuma ainda, calcula uma nova sob demanda — assim o endpoint fica
útil desde a primeira chamada, sem exigir que o cliente saiba que precisa
chamar o POST /forecast antes.
"""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_current_user
from app.core.database import get_db
from app.ml.dataset import InsufficientDataError
from app.ml.inference import ModelNotTrainedError
from app.models.project import AnalysisProject
from app.models.trend import TrendMetric
from app.models.user import User
from app.schemas.trend import TrendEstimateRead, TrendEstimatesResponse
from app.services.forecast_service import (
    ForecastHorizonError,
    generate_trend_forecast,
    get_recent_trend_estimates,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/trends", tags=["trends"])


def _get_owned_project(db: Session, project_id: uuid.UUID, user: User) -> AnalysisProject:
    project = db.get(AnalysisProject, project_id)
    if project is None or project.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado.")
    return project


@router.get(
    "/{project_id}",
    response_model=TrendEstimatesResponse,
    summary="Retorna as estimativas de tendência populacional (calcula uma se ainda não houver)",
)
async def get_trends(
    project_id: uuid.UUID,
    limit: int = Query(10, ge=1, le=100, description="Número máximo de estimativas retornadas."),
    refresh: bool = Query(
        False, description="Se True, força um novo cálculo mesmo já havendo estimativas persistidas."
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TrendEstimatesResponse:
    project = _get_owned_project(db, project_id, current_user)

    if not refresh:
        existing = get_recent_trend_estimates(db, project.id, TrendMetric.CELL_DENSITY, limit)
        if existing:
            return TrendEstimatesResponse(
                project_id=project.id,
                estimates=[TrendEstimateRead.model_validate(e) for e in existing],
                generated_fresh=False,
            )

    try:
        await run_in_threadpool(generate_trend_forecast, db, project, None, True)
    except InsufficientDataError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Ainda não há estimativas de tendência para este projeto e o histórico "
                f"disponível é insuficiente para calcular uma: {exc}"
            ),
        ) from exc
    except ModelNotTrainedError as exc:
        logger.error("Tentativa de previsão sem modelo treinado: %s", exc)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="O modelo de previsão ainda não foi treinado neste ambiente.",
        ) from exc
    except ForecastHorizonError as exc:  # pragma: no cover — não deve ocorrer com horizonte padrão
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    fresh_estimates = get_recent_trend_estimates(db, project.id, TrendMetric.CELL_DENSITY, limit)
    return TrendEstimatesResponse(
        project_id=project.id,
        estimates=[TrendEstimateRead.model_validate(e) for e in fresh_estimates],
        generated_fresh=True,
    )
