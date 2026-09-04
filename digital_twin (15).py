"""Model de Estado do Gêmeo Digital: um snapshot append-only do estado
computacional estimado de uma Culture em um dado momento.

Histórico (não uma linha mutável única) para permitir consultar a evolução
do próprio gêmeo digital ao longo do tempo (GET /digital-twin/history).

Campos nulos são intencionais: quando não há dados suficientes para estimar
uma variável, ela fica None/UNKNOWN em vez de receber um valor inventado.
"""
import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class HealthStatus(str, enum.Enum):
    """Avaliação COMPUTACIONAL do estado da cultura — não um diagnóstico
    biológico definitivo. Sempre acompanhada de `confidence`."""

    UNKNOWN = "unknown"
    NORMAL = "normal"
    WARNING = "warning"
    STRESSED = "stressed"


class DigitalTwinState(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "digital_twin_states"

    culture_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("cultures.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    culture: Mapped["Culture"] = relationship(back_populates="digital_twin_states")  # noqa: F821

    based_on_observation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("observations.id", ondelete="SET NULL"),
        nullable=True,
    )
    observation: Mapped[Optional["Observation"]] = relationship()  # noqa: F821

    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    # --- Estado estimado. None quando não há dados suficientes. ---
    biomass_estimate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    density_estimate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    morphological_state: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    environmental_state: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # "increasing" | "decreasing" | "stable" | None (heurística simples, sem ML — ver growth_heuristics.py)
    growth_state: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    health_status: Mapped[HealthStatus] = mapped_column(
        SAEnum(HealthStatus, name="health_status_enum", values_callable=lambda enum_cls: [item.value for item in enum_cls]),
        default=HealthStatus.UNKNOWN,
        nullable=False,
    )
    stress_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 0-1
    contributing_factors: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<DigitalTwinState culture_id={self.culture_id} "
            f"health_status={self.health_status} computed_at={self.computed_at}>"
        )
