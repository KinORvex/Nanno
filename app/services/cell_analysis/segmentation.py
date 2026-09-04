"""
Etapa 2 — Segmentação e detecção automática das células.

Estratégia: limiarização (Otsu ou adaptativa) -> operações morfológicas para
limpar ruído -> transformada de distância -> máximos locais como marcadores
-> watershed. O watershed é essencial para separar células que se tocam
(comum em amostras densas de cultivo), o que uma simples detecção de
contornos (cv2.findContours) não consegue fazer sozinha.
"""
import cv2
import numpy as np
from scipy import ndimage as ndi
from skimage.feature import peak_local_max
from skimage.segmentation import watershed

from app.services.cell_analysis.config import CellDetectionParams
from app.services.cell_analysis.exceptions import SegmentationError


def _binarize(enhanced_gray: np.ndarray, params: CellDetectionParams) -> np.ndarray:
    """Gera uma máscara binária (255 = célula, 0 = fundo)."""
    thresh_type = cv2.THRESH_BINARY_INV if params.cells_darker_than_background else cv2.THRESH_BINARY

    if params.threshold_method == "otsu":
        _, binary = cv2.threshold(enhanced_gray, 0, 255, thresh_type + cv2.THRESH_OTSU)
    else:
        block_size = (
            params.adaptive_block_size
            if params.adaptive_block_size % 2 == 1
            else params.adaptive_block_size + 1
        )
        binary = cv2.adaptiveThreshold(
            enhanced_gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            thresh_type,
            block_size,
            params.adaptive_c,
        )
    return binary


def _clean_binary_mask(binary: np.ndarray, params: CellDetectionParams) -> np.ndarray:
    """Remove ruído pontual (abertura) e fecha pequenos buracos dentro das células (fechamento)."""
    kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (params.morph_kernel_size, params.morph_kernel_size)
    )
    opened = cv2.morphologyEx(
        binary, cv2.MORPH_OPEN, kernel, iterations=params.morph_open_iterations
    )
    closed = cv2.morphologyEx(
        opened, cv2.MORPH_CLOSE, kernel, iterations=params.morph_close_iterations
    )
    return closed


def segment_cells(
    enhanced_gray: np.ndarray, params: CellDetectionParams = None
) -> tuple[np.ndarray, np.ndarray]:
    """
    Segmenta células individuais na imagem pré-processada.

    Retorna:
        labels: matriz int32 do mesmo tamanho da imagem, onde cada célula
                detectada recebe um rótulo inteiro único (0 = fundo).
        binary_mask: máscara binária limpa usada como base do watershed
                     (útil para debug/visualização intermediária).
    """
    params = params or CellDetectionParams()

    try:
        binary = _binarize(enhanced_gray, params)
        binary = _clean_binary_mask(binary, params)

        if not np.any(binary):
            # Campo sem nenhuma região candidata a célula — resultado válido,
            # não é um erro (ex.: amostra sem células no campo de visão).
            return np.zeros_like(enhanced_gray, dtype=np.int32), binary

        # Transformada de distância: cada pixel recebe a distância até o
        # pixel de fundo mais próximo. Os "picos" dessa transformada marcam
        # o centro aproximado de cada célula, mesmo quando elas se tocam.
        distance = ndi.distance_transform_edt(binary)

        coords = peak_local_max(
            distance,
            min_distance=params.watershed_min_distance,
            labels=binary,
        )
        mask = np.zeros(distance.shape, dtype=bool)
        mask[tuple(coords.T)] = True
        markers, _ = ndi.label(mask)

        labels = watershed(-distance, markers, mask=binary)
        return labels.astype(np.int32), binary

    except Exception as exc:  # noqa: BLE001 — traduzimos qualquer falha de CV em erro de domínio
        raise SegmentationError(f"Falha na segmentação de células: {exc}") from exc
