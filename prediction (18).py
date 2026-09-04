"""Model de Previsão: um valor futuro estimado para uma métrica de uma
Culture específica, gerado por um modelo nomeado/versionado.

Distinto de `TrendEstimate` (já existente): TrendEstimate resume uma
tendência do PROJETO INTEIRO num período (usado pelo endpoint /forecast
já existente). Prediction é pontual, por RÉPLICA/CULTURA individual, e
alimenta o módulo de previsão do gêmeo digital. Não são redundantes.

Reaproveita o enum `TrendMetric` já existente (cell_count/avg_cell_size/
cell_density) em vez de criar um enum paralelo para o mesmo conceito.
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin
from app.models.trend import TrendMetric  # reaproveitado, não duplicado


class Prediction(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "predictions"

    culture_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("cultures.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    culture: Mapped["Culture"] = relationship(back_populates="predictions")  # noqa: F821

    target_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Reaproveita o MESMO tipo Postgres "trend_metric_enum" já existente.
    metric: Mapped[TrendMetric] = mapped_column(
        SAEnum(TrendMetric, name="trend_metric_enum", values_callable=lambda enum_cls: [item.value for item in enum_cls]),
        nullable=False,
    )
    predicted_value: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    model_version: Mapped[str] = mapped_column(String(40), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Prediction culture_id={self.culture_id} metric={self.metric} "
            f"target_timestamp={self.target_timestamp}>"
        )
