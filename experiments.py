"""Endpoints CRUD de Experiment — agrupam culturas/condições dentro de um
AnalysisProject. Segue o mesmo padrão de ownership check dos demais endpoints."""
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.crud.experiment import create_experiment, get_experiment, list_experiments, update_experiment
from app.crud.project import get_project
from app.models.experiment import Experiment
from app.models.project import AnalysisProject
from app.models.user import User
from app.schemas.experiment import ExperimentCreate, ExperimentRead, ExperimentUpdate

# Rotas aninhadas em /projects/{project_id} — criação e listagem exigem o projeto explícito.
router = APIRouter(prefix="/projects/{project_id}/experiments", tags=["experiments"])
# Rotas por ID — uma vez com o experiment_id, o project_id é redundante.
detail_router = APIRouter(prefix="/experiments", tags=["experiments"])


def _get_owned_project_or_404(db: Session, project_id: uuid.UUID, user: User) -> AnalysisProject:
    project = get_project(db, project_id)
    if project is None or project.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado.")
    return project


def _get_owned_experiment(db: Session, experiment_id: uuid.UUID, user: User) -> Experiment:
    experiment = get_experiment(db, experiment_id)
    if experiment is None or experiment.project.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Experimento não encontrado.")
    return experiment


@router.post(
    "",
    response_model=ExperimentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Cria um novo experimento dentro de um projeto",
)
def create_new_experiment(
    project_id: uuid.UUID,
    experiment_in: ExperimentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Experiment:
    _get_owned_project_or_404(db, project_id, current_user)
    return create_experiment(db, project_id=project_id, experiment_in=experiment_in)


@router.get("", response_model=List[ExperimentRead], summary="Lista os experimentos de um projeto")
def list_project_experiments(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[Experiment]:
    _get_owned_project_or_404(db, project_id, current_user)
    return list_experiments(db, project_id=project_id)


@detail_router.get("/{experiment_id}", response_model=ExperimentRead, summary="Detalha um experimento")
def get_experiment_detail(
    experiment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Experiment:
    return _get_owned_experiment(db, experiment_id, current_user)


@detail_router.patch(
    "/{experiment_id}", response_model=ExperimentRead, summary="Atualiza status/descrição de um experimento"
)
def update_experiment_detail(
    experiment_id: uuid.UUID,
    experiment_in: ExperimentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Experiment:
    experiment = _get_owned_experiment(db, experiment_id, current_user)
    return update_experiment(db, experiment, experiment_in)
