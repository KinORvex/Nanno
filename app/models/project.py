"""Model de Projeto/Sessão de análise: agrupa um conjunto de imagens
de microalgas (ex.: um lote de cultivo de Nannochloropsis) analisadas
ao longo do tempo."""
import enum
import uuid
from typing import List, Optional

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class ProjectStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    COMPLETED = "completed"


class AnalysisProject(UUIDPKMixin, TimestampMixin, Base):
    """Representa uma sessão/lote de análise (ex.: 'Cultivo Tanque 3 - Ago/2026')."""

    __tablename__ = "analysis_projects"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Espécie fixa por padrão, mas mantida como campo para permitir reuso futuro
    species: Mapped[str] = mapped_column(String(120), nullable=False, default="Nannochloropsis")

    status: Mapped[ProjectStatus] = mapped_column(
        SAEnum(ProjectStatus, name="project_status_enum", values_callable=lambda enum_cls: [item.value for item in enum_cls]),
        default=ProjectStatus.ACTIVE,
        nullable=False,
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    owner: Mapped["User"] = relationship(back_populates="projects")  # noqa: F821

    images: Mapped[List["MicroalgaeImage"]] = relationship(  # noqa: F821
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="MicroalgaeImage.captured_at",
    )

    trend_estimates: Mapped[List["TrendEstimate"]] = relationship(  # noqa: F821
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    environmental_readings: Mapped[List["EnvironmentalReading"]] = relationship(  # noqa: F821
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="EnvironmentalReading.recorded_at",
    )

    # Adicionado nesta etapa: um projeto pode conter múltiplos experimentos
    # controlados (Experiment -> Culture -> Observation). Não afeta o uso
    # existente de AnalysisProject (relationship vazia por padrão).
    experiments: Mapped[List["Experiment"]] = relationship(  # noqa: F821
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Experiment.created_at",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AnalysisProject id={self.id} name={self.name!r} status={self.status}>"
