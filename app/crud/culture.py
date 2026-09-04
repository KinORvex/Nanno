"""Operações de acesso a dados para o model Culture."""
import uuid
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.culture import Culture
from app.schemas.culture import CultureCreate, CultureUpdate


def create_culture(db: Session, experiment_id: uuid.UUID, culture_in: CultureCreate) -> Culture:
    culture = Culture(experiment_id=experiment_id, **culture_in.model_dump())
    db.add(culture)
    db.commit()
    db.refresh(culture)
    return culture


def get_culture(db: Session, culture_id: uuid.UUID) -> Optional[Culture]:
    return db.get(Culture, culture_id)


def list_cultures(db: Session, experiment_id: uuid.UUID) -> List[Culture]:
    return (
        db.query(Culture)
        .filter(Culture.experiment_id == experiment_id)
        .order_by(Culture.label)
        .all()
    )


def update_culture(db: Session, culture: Culture, culture_in: CultureUpdate) -> Culture:
    for field, value in culture_in.model_dump(exclude_unset=True).items():
        setattr(culture, field, value)
    db.commit()
    db.refresh(culture)
    return culture
