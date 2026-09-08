"""Model de estimativas de tendência: séries calculadas periodicamente a partir
das métricas das imagens de um projeto (ex.: crescimento populacional,
variação do tamanho médio de células ao longo do tempo)."""
import enum
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


class TrendDirection(str, enum.Enum):
    INCREASING = "increasing"
    DECREASING = "decreasing"
    STABLE = "stable"
    INSUFFICIENT_DATA = "insufficient_data"


class TrendMetric(str, enum.Enum):
    CELL_COUNT = "cell_count"
    AVG_CELL_SIZE = "avg_cell_size"
    CELL_DENSITY = "cell_density"


class TrendEstimate(UUIDPKMixin, TimestampMixin, Base):
    """Resultado agregado de uma janela de tempo (ex.: 'densidade celular
    cresceu 12% na última semana')."""

    __tablename__ = "trend_estimates"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("analysis_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project: Mapped["AnalysisProject"] = relationship(back_populates="trend_estimates")  # noqa: F821

     metric: Mapped[TrendMetric] = mapped_column(
        SAEnum(TrendMetric, name="trend_metric_enum", values_callable=lambda enum_cls: [item.value for item in enum_cls]), nullable=False
    )
    direction: Mapped[TrendDirection] = mapped_column(
        SAEnum(TrendDirection, name="trend_direction_enum", values_callable=lambda enum_cls: [item.value for item in enum_cls]), nullable=False
    )

    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Valor absoluto no início/fim do período e variação percentual calculada
    value_start: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    value_end: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    percent_change: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Nome/versão do método estatístico usado (ex.: "linear_regression_v1")
    method: Mapped[str] = mapped_column(String(120), nullable=False, default="linear_regression_v1")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<TrendEstimate project_id={self.project_id} metric={self.metric} "
            f"direction={self.direction}>"
        )
