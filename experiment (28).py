"""Operações de acesso a dados para o model Experiment."""
import uuid
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.experiment import Experiment
from app.schemas.experiment import ExperimentCreate, ExperimentUpdate


def create_experiment(db: Session, project_id: uuid.UUID, experiment_in: ExperimentCreate) -> Experiment:
    experiment = Experiment(project_id=project_id, **experiment_in.model_dump())
    db.add(experiment)
    db.commit()
    db.refresh(experiment)
    return experiment


def get_experiment(db: Session, experiment_id: uuid.UUID) -> Optional[Experiment]:
    return db.get(Experiment, experiment_id)


def list_experiments(db: Session, project_id: uuid.UUID) -> List[Experiment]:
    return (
        db.query(Experiment)
        .filter(Experiment.project_id == project_id)
        .order_by(Experiment.created_at.desc())
        .all()
    )


def update_experiment(db: Session, experiment: Experiment, experiment_in: ExperimentUpdate) -> Experiment:
    for field, value in experiment_in.model_dump(exclude_unset=True).items():
        setattr(experiment, field, value)
    db.commit()
    db.refresh(experiment)
    return experiment
