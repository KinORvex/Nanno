"""Model de Análise de Imagem: uma execução VERSIONADA do pipeline de visão
computacional sobre uma imagem específica.

Decisão de design: separado de `MicroalgaeImage` (que continua guardando os
campos "resumo" usados pelo endpoint /analyze já existente, intocado) para
permitir reprocessar a mesma imagem com uma versão nova do algoritmo sem
perder o histórico de análises anteriores — rastreabilidade/reprodutibilidade
(item 11 da especificação).

Decisão sobre `metrics` (JSON, não colunas normalizadas): novas métricas
morfológicas devem poder ser adicionadas sem migração de schema a cada vez
(exigência explícita do escopo). O formato é versionado por `algorithm_version`
— consumidores sabem como interpretar o JSON a partir da versão registrada.
Formato "v1" (mesma nomenclatura usada pelo pipeline `cell_analysis` já
existente, não reinventada):
    {
      "cell_count": int,
      "diameter_mean_um": float, "diameter_median_um": float,
      "diameter_std_um": float, "diameter_cv": float,
      "diameter_p25_um": float, "diameter_p75_um": float,
      "area_mean_um2": float,
      "avg_confidence_score": float,
      "cell_density_cells_per_ml": float | None
    }
"""
import uuid
from typing import Optional

from sqlalchemy import JSON, Enum as SAEnum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.image import ProcessingStatus  # reaproveitado, não duplicado
from app.models.mixins import TimestampMixin, UUIDPKMixin


class ImageAnalysis(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "image_analyses"

    image_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("microalgae_images.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    image: Mapped["MicroalgaeImage"] = relationship()  # noqa: F821

    observation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("observations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    observation: Mapped[Optional["Observation"]] = relationship(back_populates="analyses")  # noqa: F821

    # Reaproveita o MESMO tipo Postgres "processing_status_enum" já criado
    # pela migration original de MicroalgaeImage (ver migration desta etapa).
    status: Mapped[ProcessingStatus] = mapped_column(
        SAEnum(ProcessingStatus, name="processing_status_enum", values_callable=lambda enum_cls: [item.value for item in enum_cls]),
        default=ProcessingStatus.PENDING,
        nullable=False,
        index=True,
    )
    processing_error: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)

    # --- Versionamento / reprodutibilidade ---
    algorithm_name: Mapped[str] = mapped_column(String(120), nullable=False, default="nannochloropsis_watershed")
    algorithm_version: Mapped[str] = mapped_column(String(40), nullable=False, default="v1")
    preprocessing_version: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    segmentation_version: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    parameters: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # CellDetectionParams usados

    # --- Métricas extraídas — JSON estruturado e versionado (ver docstring) ---
    metrics: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ImageAnalysis id={self.id} image_id={self.image_id} status={self.status}>"
