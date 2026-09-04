"""Desenha as marcações visuais (bounding circles) sobre a imagem original,
gerando o artefato que será salvo de volta no S3 para inspeção humana."""
from typing import List, Tuple

import cv2
import numpy as np

from app.services.cell_analysis.config import CellDetectionParams
from app.services.cell_analysis.metrics import CellMeasurement


def draw_cell_annotations(
    original_bgr: np.ndarray,
    measurements: List[CellMeasurement],
    params: CellDetectionParams = None,
) -> np.ndarray:
    """
    Desenha um círculo delimitador em cada célula detectada (raio em pixels,
    convertido de volta a partir do raio em µm usando a mesma escala de
    calibração) e um contador no canto da imagem.
    """
    params = params or CellDetectionParams()
    annotated = original_bgr.copy()
    scale = params.microns_per_pixel

    for m in measurements:
        radius_px = max(1, int(round((m.equivalent_radius_um / scale))))
        center: Tuple[int, int] = (int(round(m.centroid_x_px)), int(round(m.centroid_y_px)))
        cv2.circle(
            annotated,
            center,
            radius_px,
            params.annotation_circle_color_bgr,
            params.annotation_circle_thickness,
        )

    _draw_summary_banner(annotated, cell_count=len(measurements), params=params)
    return annotated


def _draw_summary_banner(image: np.ndarray, cell_count: int, params: CellDetectionParams) -> None:
    text = f"Celulas detectadas: {cell_count}"
    font = cv2.FONT_HERSHEY_SIMPLEX
    (text_w, text_h), baseline = cv2.getTextSize(text, font, params.annotation_font_scale, 1)

    padding = 8
    cv2.rectangle(
        image,
        (0, 0),
        (text_w + 2 * padding, text_h + baseline + 2 * padding),
        (0, 0, 0),
        thickness=-1,
    )
    cv2.putText(
        image,
        text,
        (padding, text_h + padding),
        font,
        params.annotation_font_scale,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )


def encode_image(image_bgr: np.ndarray, extension: str = ".png") -> bytes:
    """Codifica a imagem anotada de volta em bytes, prontos para upload no S3."""
    success, buffer = cv2.imencode(extension, image_bgr)
    if not success:
        raise ValueError(f"Falha ao codificar imagem no formato '{extension}'.")
    return buffer.tobytes()
