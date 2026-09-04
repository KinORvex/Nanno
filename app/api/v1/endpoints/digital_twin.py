"""Endpoints do Gêmeo Digital: estado atual, histórico de estados,
avaliação de estresse e previsões de uma Culture."""
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.crud.culture import get_culture
from app.models.culture import Culture
from app.models.digital_twin import DigitalTwinState, HealthStatus
from app.models.prediction import Prediction
from app.models.user import User
from app.schemas.digital_twin import DigitalTwinHistoryResponse, DigitalTwinStateRead, StressAssessmentResponse
from app.schemas.prediction import PredictionRead
from app.services.digital_twin.digital_twin_service import compute_digital_twin_state

router = APIRouter(prefix="/cultures/{culture_id}", tags=["digital-twin"])


def _get_owned_culture(db: Session, culture_id: uuid.UUID, user: User) -> Culture:
    culture = get_culture(db, culture_id)
    if culture is None or culture.experiment.project.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cultura não encontrada.")
    return culture


@router.get(
    "/digital-twin", response_model=DigitalTwinStateRead,
    summary="Calcula e retorna o estado atual do gêmeo digital da cultura (persiste um novo snapshot)",
)
def get_current_digital_twin_state(
    culture_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DigitalTwinState:
    culture = _get_owned_culture(db, culture_id, current_user)
    return compute_digital_twin_state(db, culture, persist=True)


@router.get(
    "/digital-twin/history", response_model=DigitalTwinHistoryResponse,
    summary="Retorna o histórico de estados já calculados do gêmeo digital (não recalcula)",
)
def get_digital_twin_history(
    culture_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DigitalTwinHistoryResponse:
    culture = _get_owned_culture(db, culture_id, current_user)
    states = sorted(culture.digital_twin_states, key=lambda s: s.computed_at)
    return DigitalTwinHistoryResponse(culture_id=culture.id, states=states)


@router.get(
    "/stress-assessment", response_model=StressAssessmentResponse,
    summary="Calcula e retorna a avaliação de estresse mais recente da cultura",
)
def get_stress_assessment(
    culture_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StressAssessmentResponse:
    culture = _get_owned_culture(db, culture_id, current_user)
    state = compute_digital_twin_state(db, culture, persist=True)
    return StressAssessmentResponse(
        culture_id=culture.id,
        computed_at=state.computed_at,
        health_status=state.health_status,
        stress_score=state.stress_score,
        confidence=state.confidence,
        contributing_factors=state.contributing_factors,
        message=(
            None
            if state.health_status != HealthStatus.UNKNOWN
            else "Dados insuficientes para uma avaliação de estresse cientificamente confiável."
        ),
    )


@router.get(
    "/predictions", response_model=List[PredictionRead],
    summary="Lista as previsões já geradas para a cultura (não calcula novas)",
)
def list_culture_predictions(
    culture_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[Prediction]:
    culture = _get_owned_culture(db, culture_id, current_user)
    return sorted(culture.predictions, key=lambda p: p.created_at, reverse=True)
