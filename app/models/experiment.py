"""Model de Experimento: agrupa múltiplas culturas/condições experimentais
dentro de um AnalysisProject, permitindo comparação controlada entre
condições (ex.: controle vs. privação de nitrogênio)."""
import enum
import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class ExperimentStatus(str, enum.Enum):
    PLANNING = "planning"
    ACTIVE = "active"
    COMPLETED = "completed"
    ABORTED = "aborted"


class Experiment(UUIDPKMixin, TimestampMixin, Base):
    """Um experimento controlado dentro de um projeto (ex.: 'Privação de
    nitrogênio - Ago/2026'), agrupando múltiplas culturas/condições (Culture)."""

    __tablename__ = "experiments"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("analysis_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project: Mapped["AnalysisProject"] = relationship(back_populates="experiments")  # noqa: F821

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    hypothesis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    status: Mapped[ExperimentStatus] = mapped_column(
        SAEnum(ExperimentStatus, name="experiment_status_enum"),
        default=ExperimentStatus.PLANNING,
        nullable=False,
    )

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    cultures: Mapped[List["Culture"]] = relationship(  # noqa: F821
        back_populates="experiment",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Culture.label",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Experiment id={self.id} name={self.name!r} status={self.status}>"
