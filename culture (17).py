"""Model de Cultura/Condição experimental (ex.: C1, N1) dentro de um Experiment."""
import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class Culture(UUIDPKMixin, TimestampMixin, Base):
    """Uma réplica/condição individual dentro de um experimento (ex.: 'C1', 'N2').

    `condition_label` é texto livre (não um enum fixo) deliberadamente: o
    conjunto de condições experimentais possíveis (controle, privação de
    nitrogênio, privação de fósforo, choque de salinidade etc.) deve poder
    crescer sem exigir migração de schema a cada novo tipo de experimento.
    """

    __tablename__ = "cultures"

    experiment_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("experiments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    experiment: Mapped["Experiment"] = relationship(back_populates="cultures")  # noqa: F821

    label: Mapped[str] = mapped_column(String(50), nullable=False)  # ex.: "C1", "N2"
    condition_label: Mapped[str] = mapped_column(String(120), nullable=False)  # ex.: "controle", "privacao_nitrogenio"
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # T0 (início da observação) e Tstress (início do tratamento, quando
    # aplicável) — permitem calcular tempo relativo sem depender
    # exclusivamente de timestamp absoluto (ver Observation.relative_hours).
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    stress_induced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    observations: Mapped[List["Observation"]] = relationship(  # noqa: F821
        back_populates="culture",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Observation.observed_at",
    )
    digital_twin_states: Mapped[List["DigitalTwinState"]] = relationship(  # noqa: F821
        back_populates="culture",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="DigitalTwinState.computed_at",
    )
    predictions: Mapped[List["Prediction"]] = relationship(  # noqa: F821
        back_populates="culture",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Prediction.created_at",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Culture id={self.id} label={self.label!r} condition={self.condition_label!r}>"
