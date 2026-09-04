"""Endpoints CRUD de AnalysisProject — todas as rotas protegidas por JWT e
com verificação de propriedade (um usuário só vê/edita seus próprios projetos)."""
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.crud.project import (
    create_project,
    delete_project,
    get_project,
    list_projects_with_summary,
    update_project,
)
from app.models.project import AnalysisProject
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectRead, ProjectSummary, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["projects"])


def _get_owned_project(db: Session, project_id: uuid.UUID, user: User) -> AnalysisProject:
    project = get_project(db, project_id)
    if project is None or project.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado.")
    return project


@router.post(
    "",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
    summary="Cria um novo projeto/sessão de análise",
)
def create_new_project(
    project_in: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AnalysisProject:
    return create_project(db, owner_id=current_user.id, project_in=project_in)


@router.get(
    "",
    response_model=List[ProjectSummary],
    summary="Lista os projetos do usuário autenticado, com contadores agregados",
)
def list_my_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[ProjectSummary]:
    return list_projects_with_summary(db, owner_id=current_user.id)


@router.get("/{project_id}", response_model=ProjectRead, summary="Detalha um projeto específico")
def get_project_detail(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AnalysisProject:
    return _get_owned_project(db, project_id, current_user)


@router.patch("/{project_id}", response_model=ProjectRead, summary="Atualiza nome, descrição ou status")
def update_project_detail(
    project_id: uuid.UUID,
    project_in: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AnalysisProject:
    project = _get_owned_project(db, project_id, current_user)
    return update_project(db, project, project_in)


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove um projeto e todos os seus dados associados (imagens, tendências, leituras)",
)
def delete_project_detail(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    project = _get_owned_project(db, project_id, current_user)
    delete_project(db, project)
