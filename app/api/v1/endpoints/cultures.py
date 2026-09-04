"""Endpoints de Culture (réplica/condição experimental): CRUD, histórico
temporal (GET /cultures/{id}/history) e comparação entre culturas.

ATENÇÃO À ORDEM DAS ROTAS: `/cultures/compare` é registrada ANTES de
`/cultures/{culture_id}` propositalmente — em FastAPI/Starlette, rotas são
casadas na ordem de registro, e uma rota dinâmica `{culture_id}` registrada
antes capturaria "compare" como se fosse um UUID (gerando 422 em vez de
executar a comparação).
"""
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.crud.culture import create_culture, get_culture, list_cultures
from app.models.culture import Culture
from app.models.experiment import Experiment
from app.models.user import User
from app.schemas.culture import (
    CultureComparisonResponse,
    CultureCreate,
    CultureHistoryPoint,
    CultureHistoryResponse,
    CultureRead,
    EnvironmentalSnapshot,
)

router = APIRouter(prefix="/experiments/{experiment_id}/cultures", tags=["cultures"])
detail_router = APIRouter(prefix="/cultures", tags=["cultures"])


def _get_owned_experiment(db: Session, experiment_id: uuid.UUID, user: User) -> Experiment:
    experiment = db.get(Experiment, experiment_id)
    if experiment is None or experiment.project.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Experimento não encontrado.")
    return experiment


def _get_owned_culture(db: Session, culture_id: uuid.UUID, user: User) -> Culture:
    culture = get_culture(db, culture_id)
    if culture is None or culture.experiment.project.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cultura não encontrada.")
    return culture


@router.post(
    "", response_model=CultureRead, status_code=status.HTTP_201_CREATED,
    summary="Cria uma cultura/condição experimental dentro de um experimento",
)
def create_new_culture(
    experiment_id: uuid.UUID,
    culture_in: CultureCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Culture:
    _get_owned_experiment(db, experiment_id, current_user)
    return create_culture(db, experiment_id=experiment_id, culture_in=culture_in)


@router.get("", response_model=List[CultureRead], summary="Lista as culturas de um experimento")
def list_experiment_cultures(
    experiment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[Culture]:
    _get_owned_experiment(db, experiment_id, current_user)
    return list_cultures(db, experiment_id=experiment_id)


def _build_history(culture: Culture) -> CultureHistoryResponse:
    points = []
    for obs in sorted(culture.observations, key=lambda o: o.observed_at):
        analyses = [a for a in obs.analyses if a.metrics]
        latest_metrics = max(analyses, key=lambda a: a.created_at).metrics if analyses else None

        env_snapshot = (
            EnvironmentalSnapshot.model_validate(obs.environmental_reading)
            if obs.environmental_reading is not None
            else None
        )

        latest_twin_state = None
        candidates = [s for s in culture.digital_twin_states if s.based_on_observation_id == obs.id]
        if candidates:
            latest_twin_state = max(candidates, key=lambda s: s.computed_at).health_status.value

        points.append(
            CultureHistoryPoint(
                observation_id=obs.id,
                observed_at=obs.observed_at,
                relative_hours=obs.relative_hours,
                metrics=latest_metrics,
                environmental_conditions=env_snapshot,
                health_state=latest_twin_state,
            )
        )

    return CultureHistoryResponse(
        culture_id=culture.id, label=culture.label, condition_label=culture.condition_label, points=points
    )


# --- Rota estática ANTES da rota dinâmica {culture_id} (ver docstring do módulo) ---
@detail_router.get(
    "/compare", response_model=CultureComparisonResponse,
    summary="Compara o histórico de duas ou mais culturas lado a lado",
)
def compare_cultures(
    ids: List[uuid.UUID] = Query(..., description="IDs das culturas a comparar (ex.: ?ids=uuid1&ids=uuid2)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CultureComparisonResponse:
    if len(ids) < 2:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Informe ao menos duas culturas para comparar.")
    cultures = [_get_owned_culture(db, culture_id, current_user) for culture_id in ids]
    return CultureComparisonResponse(cultures=[_build_history(c) for c in cultures])


@detail_router.get("/{culture_id}", response_model=CultureRead, summary="Detalha uma cultura")
def get_culture_detail(
    culture_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Culture:
    return _get_owned_culture(db, culture_id, current_user)


@detail_router.get(
    "/{culture_id}/history", response_model=CultureHistoryResponse,
    summary="Retorna a série temporal completa de uma cultura (métricas + ambiente + estado de saúde)",
)
def get_culture_history(
    culture_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CultureHistoryResponse:
    culture = _get_owned_culture(db, culture_id, current_user)
    return _build_history(culture)
