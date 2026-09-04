"""Schemas Pydantic para o endpoint de análise de imagem (/analyze)."""
import uuid
from typing import List, Optional

from pydantic import BaseModel


class SizeDistributionStats(BaseModel):
    mean: Optional[float] = None
    median: Optional[float] = None
    std: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    p25: Optional[float] = None
    p75: Optional[float] = None


class AreaDistributionStats(BaseModel):
    mean: Optional[float] = None
    median: Optional[float] = None
    std: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None


class AnalyzeImageResponse(BaseModel):
    image_id: uuid.UUID
    project_id: uuid.UUID

    cell_count: int
    diameter_um: SizeDistributionStats
    area_um2: AreaDistributionStats
    avg_confidence_score: Optional[float] = None
    cell_density_cells_per_ml: Optional[float] = None

    # Diâmetro individual (µm) de cada célula detectada — usado pelo frontend
    # para montar o histograma real de distribuição de tamanhos (as
    # estatísticas acima, sozinhas, não permitem reconstruir a forma da distribuição).
    diameters_um: List[float] = []

    processing_time_ms: float
    microns_per_pixel: float

    original_s3_key: str
    annotated_s3_key: str
    annotated_image_download_url: str
