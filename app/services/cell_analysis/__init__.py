"""
Modulo de analise de imagens de microalgas (Nannochloropsis) via OpenCV +
scikit-image: pre-processamento, segmentacao (watershed), contagem e
distribuicao de tamanhos de celulas.

Uso tipico:

    from app.services.cell_analysis import analyze_nannochloropsis_image

    result = analyze_nannochloropsis_image(image_bytes)
    json_payload = result.to_dict()
    annotated_png_bytes = result.annotated_image_bytes

Para imagens que ja estao no S3, use `analyze_image_from_s3`.
"""
from app.services.cell_analysis.config import CellDetectionParams, DEFAULT_PARAMS
from app.services.cell_analysis.exceptions import (
    CellAnalysisError,
    InvalidImageError,
    SegmentationError,
)
from app.services.cell_analysis.metrics import CellMeasurement
from app.services.cell_analysis.pipeline import AnalysisResult, analyze_nannochloropsis_image
from app.services.cell_analysis.s3_integration import analyze_image_from_s3

__all__ = [
    "CellDetectionParams",
    "DEFAULT_PARAMS",
    "CellAnalysisError",
    "InvalidImageError",
    "SegmentationError",
    "CellMeasurement",
    "AnalysisResult",
    "analyze_nannochloropsis_image",
    "analyze_image_from_s3",
]
