"""
Pipeline principal de análise de imagens de Nannochloropsis.

Ponto de entrada único do módulo: recebe bytes de imagem (baixados do S3 ou
de qualquer outra origem) e devolve um resultado estruturado (dict
JSON-serializável) mais a imagem anotada em bytes, pronta para upload.

Este arquivo NÃO depende de S3/boto3/SQLAlchemy — a integração com
infraestrutura fica em `s3_integration.py`, mantendo a lógica de visão
computacional pura e fácil de testar unitariamente (basta passar bytes de
uma imagem de teste).
"""
import logging
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np

from app.services.cell_analysis.config import CellDetectionParams
from app.services.cell_analysis.exceptions import CellAnalysisError, InvalidImageError
from app.services.cell_analysis.metrics import (
    CellMeasurement,
    compute_summary_statistics,
    estimate_cell_density,
    extract_cell_measurements,
)
from app.services.cell_analysis.preprocessing import load_image_from_bytes, preprocess_image
from app.services.cell_analysis.segmentation import segment_cells
from app.services.cell_analysis.visualization import draw_cell_annotations, encode_image

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    """Resultado completo de uma análise, pronto para persistência e resposta de API."""

    cell_count: int
    summary: dict
    measurements: list[CellMeasurement]
    annotated_image_bytes: bytes
    processing_time_ms: float
    params_used: CellDetectionParams

    def to_dict(self, include_individual_measurements: bool = True) -> dict:
        """
        Serializa o resultado em um dicionário JSON-compatível.

        `include_individual_measurements=False` é útil quando se quer apenas
        o resumo estatístico (ex.: para preencher `MicroalgaeImageMetricsUpdate`),
        sem a lista completa de células — que pode ser grande em amostras densas.
        """
        result = {
            "cell_count": self.cell_count,
            "summary": self.summary,
            "processing_time_ms": round(self.processing_time_ms, 2),
            "microns_per_pixel": self.params_used.microns_per_pixel,
        }
        if include_individual_measurements:
            result["measurements"] = [m.to_dict() for m in self.measurements]
        return result


def analyze_nannochloropsis_image(
    image_bytes: bytes,
    params: Optional[CellDetectionParams] = None,
    sample_volume_context: Optional[dict] = None,
) -> AnalysisResult:
    """
    Executa o pipeline completo de análise sobre uma imagem de microscopia.

    Args:
        image_bytes: conteúdo bruto do arquivo de imagem (PNG/JPEG/TIFF).
        params: parâmetros de calibração/detecção. Usa os padrões de
            Nannochloropsis se omitido — mas `microns_per_pixel` DEVE ser
            ajustado para a objetiva/câmera real do laboratório.
        sample_volume_context: opcional, dict com `chamber_depth_um` e
            `dilution_factor` para estimar `cell_density_cells_per_ml`.
            Sem isso, a densidade não é calculada (retorna None).

    Returns:
        AnalysisResult com contagem, estatísticas de tamanho, medições
        individuais e a imagem anotada (bytes PNG) para upload no S3.

    Raises:
        InvalidImageError: imagem corrompida/vazia/ilegível.
        SegmentationError: falha durante a segmentação.
    """
    params = params or CellDetectionParams()
    started_at = time.perf_counter()

    try:
        original_bgr = load_image_from_bytes(image_bytes)
        enhanced_gray = preprocess_image(original_bgr, params)
        labels, _binary_mask = segment_cells(enhanced_gray, params)
        measurements = extract_cell_measurements(labels, params)
        summary = compute_summary_statistics(measurements)

        if sample_volume_context:
            height_px, width_px = original_bgr.shape[:2]
            image_area_um2 = (width_px * params.microns_per_pixel) * (
                height_px * params.microns_per_pixel
            )
            density = estimate_cell_density(
                cell_count=len(measurements),
                image_area_um2=image_area_um2,
                chamber_depth_um=sample_volume_context.get("chamber_depth_um", 0),
                dilution_factor=sample_volume_context.get("dilution_factor", 1.0),
            )
            summary["cell_density_cells_per_ml"] = density
        else:
            summary["cell_density_cells_per_ml"] = None

        annotated_bgr = draw_cell_annotations(original_bgr, measurements, params)
        annotated_bytes = encode_image(annotated_bgr, extension=".png")

    except InvalidImageError:
        raise
    except CellAnalysisError:
        raise
    except Exception as exc:  # noqa: BLE001 — última barreira: nunca vazar exceção não tratada do CV
        logger.exception("Falha inesperada no pipeline de análise de imagem")
        raise CellAnalysisError(f"Falha inesperada ao processar a imagem: {exc}") from exc

    elapsed_ms = (time.perf_counter() - started_at) * 1000

    logger.info(
        "Análise concluída: %d células detectadas em %.1fms", len(measurements), elapsed_ms
    )

    return AnalysisResult(
        cell_count=len(measurements),
        summary=summary,
        measurements=measurements,
        annotated_image_bytes=annotated_bytes,
        processing_time_ms=elapsed_ms,
        params_used=params,
    )
