"""Model de Observação: um ponto no tempo de acompanhamento de uma Culture,
associando imagens e a condição ambiental medida naquele momento."""
import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class Observation(UUIDPKMixin, TimestampMixin, Base):
    """Um timepoint de uma Culture (ex.: 'C1 às 48h'). Não guarda métricas
    diretamente — elas vivem em ImageAnalysis, associada às imagens desta
    observação; Observation é o nó que amarra tempo + ambiente + imagens.

    Reaproveita o model `EnvironmentalReading` já existente via FK opcional,
    em vez de duplicar campos de temperatura/pH/luz aqui.
    """

    __tablename__ = "observations"

    culture_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("cultures.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    culture: Mapped["Culture"] = relationship(back_populates="observations")  # noqa: F821

    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    # Tempo relativo ao início da cultura (culture.started_at), em horas.
    # Calculado no momento da criação (ver crud/observation.py), mas
    # armazenado explicitamente — não depende exclusivamente do timestamp
    # absoluto para reconstrução de séries temporais.
    relative_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    environmental_reading_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("environmental_readings.id", ondelete="SET NULL"),
        nullable=True,
    )
    environmental_reading: Mapped[Optional["EnvironmentalReading"]] = relationship()  # noqa: F821

    images: Mapped[List["MicroalgaeImage"]] = relationship(  # noqa: F821
        back_populates="observation",
        passive_deletes=True,
    )
    analyses: Mapped[List["ImageAnalysis"]] = relationship(  # noqa: F821
        back_populates="observation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Observation id={self.id} culture_id={self.culture_id} observed_at={self.observed_at}>"
