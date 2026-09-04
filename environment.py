"""Model de leitura ambiental: medições de condições de cultivo (temperatura,
pH, luminosidade, salinidade) usadas como features exógenas no modelo de
previsão de tendência populacional. Independente das imagens — pode vir de
sensores/IoT ou de registro manual do operador."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class EnvironmentalReading(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "environmental_readings"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("analysis_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project: Mapped["AnalysisProject"] = relationship(back_populates="environmental_readings")  # noqa: F821

    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    temperature_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ph: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    salinity_psu: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    light_intensity_umol_m2_s: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    dissolved_oxygen_mg_l: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<EnvironmentalReading project_id={self.project_id} recorded_at={self.recorded_at}>"
