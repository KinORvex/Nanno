"""Model de imagem de microalgas: metadados do arquivo (armazenado no S3) e
os resultados quantitativos extraídos pelo pipeline de visão computacional
(contagem de células, tamanho médio, densidade etc.)."""
import enum
import uuid
from typing import Optional

from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class ProcessingStatus(str, enum.Enum):
    PENDING = "pending"        # upload recebido, aguardando processamento
    PROCESSING = "processing"  # pipeline de CV em execução
    COMPLETED = "completed"    # métricas extraídas com sucesso
    FAILED = "failed"          # erro no processamento


class MicroalgaeImage(UUIDPKMixin, TimestampMixin, Base):
    """Uma imagem de microscopia enviada para análise, e suas métricas derivadas."""

    __tablename__ = "microalgae_images"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("analysis_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project: Mapped["AnalysisProject"] = relationship(back_populates="images")  # noqa: F821

    # --- Metadados do arquivo / armazenamento (S3) ---
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    s3_bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    s3_key: Mapped[str] = mapped_column(String(1000), nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    width_px: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height_px: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Data/hora em que a imagem foi capturada no microscópio (pode diferir do upload)
    captured_at: Mapped[Optional[DateTime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Status do pipeline de análise ---
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        SAEnum(ProcessingStatus, name="processing_status_enum", values_callable=lambda enum_cls: [item.value for item in enum_cls]),
        default=ProcessingStatus.PENDING,
        nullable=False,
        index=True,
    )
    processing_error: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)

    # --- Métricas extraídas (preenchidas após o processamento) ---
    cell_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    avg_cell_diameter_um: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    std_cell_diameter_um: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cell_density_cells_per_ml: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 0-1

    # Payload flexível para métricas adicionais do modelo de CV (histograma de
    # tamanhos, bounding boxes, versão do modelo etc.) sem precisar migrar o schema.
    extra_metrics: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # --- Adicionado nesta etapa: vínculo opcional a uma Observation de um
    # --- experimento controlado. NULLABLE: imagens enviadas pelo endpoint
    # --- /analyze existente (sem contexto de experimento) continuam
    # --- funcionando exatamente como antes, sem preencher este campo.
    observation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("observations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    observation: Mapped[Optional["Observation"]] = relationship(  # noqa: F821
        back_populates="images"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<MicroalgaeImage id={self.id} status={self.processing_status} "
            f"cell_count={self.cell_count}>"
        )
