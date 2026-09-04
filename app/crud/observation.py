"""Operações de acesso a dados para o model Observation."""
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.culture import Culture
from app.models.observation import Observation
from app.schemas.observation import ObservationCreate


def _compute_relative_hours(culture: Culture, observed_at: datetime) -> Optional[float]:
    """Calcula horas desde culture.started_at (T0). Retorna None se T0 não
    estiver definido — o timestamp absoluto (observed_at) continua
    disponível para reconstrução de séries temporais mesmo sem T0."""
    if culture.started_at is None:
        return None
    delta = observed_at - culture.started_at
    return delta.total_seconds() / 3600.0


def create_observation(db: Session, culture: Culture, observation_in: ObservationCreate) -> Observation:
    observed_at = observation_in.observed_at or datetime.now(timezone.utc)
    observation = Observation(
        culture_id=culture.id,
        observed_at=observed_at,
        relative_hours=_compute_relative_hours(culture, observed_at),
        notes=observation_in.notes,
        environmental_reading_id=observation_in.environmental_reading_id,
    )
    db.add(observation)
    db.commit()
    db.refresh(observation)
    return observation


def get_observation(db: Session, observation_id: uuid.UUID) -> Optional[Observation]:
    return db.get(Observation, observation_id)


def list_observations(db: Session, culture_id: uuid.UUID) -> List[Observation]:
    return (
        db.query(Observation)
        .filter(Observation.culture_id == culture_id)
        .order_by(Observation.observed_at)
        .all()
    )
