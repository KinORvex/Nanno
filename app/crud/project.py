"""Operações de acesso a dados para o model AnalysisProject."""
import uuid
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.image import MicroalgaeImage
from app.models.project import AnalysisProject
from app.schemas.project import ProjectCreate, ProjectSummary, ProjectUpdate


def create_project(db: Session, owner_id: uuid.UUID, project_in: ProjectCreate) -> AnalysisProject:
    project = AnalysisProject(
        owner_id=owner_id,
        name=project_in.name,
        description=project_in.description,
        species=project_in.species,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def get_project(db: Session, project_id: uuid.UUID) -> Optional[AnalysisProject]:
    return db.get(AnalysisProject, project_id)


def list_projects_with_summary(db: Session, owner_id: uuid.UUID) -> List[ProjectSummary]:
    """
    Lista os projetos do usuário com contadores agregados (nº de imagens e
    a contagem de células da imagem mais recente), evitando N+1 queries ao
    calcular esses agregados em uma única passada por projeto.
    """
    projects = (
        db.query(AnalysisProject)
        .filter(AnalysisProject.owner_id == owner_id)
        .order_by(AnalysisProject.created_at.desc())
        .all()
    )
    if not projects:
        return []

    project_ids = [p.id for p in projects]

    image_counts = dict(
        db.query(MicroalgaeImage.project_id, func.count(MicroalgaeImage.id))
        .filter(MicroalgaeImage.project_id.in_(project_ids))
        .group_by(MicroalgaeImage.project_id)
        .all()
    )

    latest_images = dict(
        db.query(MicroalgaeImage.project_id, func.max(MicroalgaeImage.created_at))
        .filter(MicroalgaeImage.project_id.in_(project_ids))
        .group_by(MicroalgaeImage.project_id)
        .all()
    )
    latest_cell_counts: dict = {}
    for project_id, latest_created_at in latest_images.items():
        if latest_created_at is None:
            continue
        latest_image = (
            db.query(MicroalgaeImage)
            .filter(
                MicroalgaeImage.project_id == project_id,
                MicroalgaeImage.created_at == latest_created_at,
            )
            .first()
        )
        latest_cell_counts[project_id] = latest_image.cell_count if latest_image else None

    return [
        ProjectSummary(
            id=p.id,
            name=p.name,
            description=p.description,
            species=p.species,
            status=p.status,
            owner_id=p.owner_id,
            created_at=p.created_at,
            updated_at=p.updated_at,
            image_count=image_counts.get(p.id, 0),
            latest_cell_count=latest_cell_counts.get(p.id),
        )
        for p in projects
    ]


def update_project(db: Session, project: AnalysisProject, project_in: ProjectUpdate) -> AnalysisProject:
    update_data = project_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)
    db.commit()
    db.refresh(project)
    return project


def delete_project(db: Session, project: AnalysisProject) -> None:
    db.delete(project)
    db.commit()
