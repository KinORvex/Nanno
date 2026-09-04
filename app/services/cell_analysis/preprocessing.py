"""
Etapa 1 — Pré-processamento da imagem microscópica.

Pipeline: escala de cinza -> normalização -> remoção de ruído -> equalização
adaptativa de contraste (CLAHE). Cada etapa reduz artefatos que atrapalham a
segmentação (ruído de sensor, iluminação desigual do campo do microscópio).
"""
import cv2
import numpy as np

from app.services.cell_analysis.config import CellDetectionParams
from app.services.cell_analysis.exceptions import InvalidImageError


def load_image_from_bytes(image_bytes: bytes) -> np.ndarray:
    """Decodifica bytes brutos (ex.: baixados do S3) em uma imagem BGR (formato OpenCV)."""
    if not image_bytes:
        raise InvalidImageError("Buffer de imagem vazio.")

    buffer = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)

    if image is None:
        raise InvalidImageError(
            "Não foi possível decodificar a imagem — arquivo corrompido ou formato não suportado."
        )
    if image.shape[0] < 10 or image.shape[1] < 10:
        raise InvalidImageError(f"Dimensões de imagem inválidas: {image.shape[:2]}")

    return image


def to_grayscale(image_bgr: np.ndarray) -> np.ndarray:
    if image_bgr.ndim == 2:
        return image_bgr
    return cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)


def preprocess_image(image_bgr: np.ndarray, params: CellDetectionParams = None) -> np.ndarray:
    """
    Aplica normalização, remoção de ruído e ajuste de contraste.

    Retorna uma imagem em escala de cinza (uint8) pronta para a etapa de
    segmentação. A imagem original (colorida) é preservada pelo chamador
    para uso posterior na visualização das marcações.
    """
    params = params or CellDetectionParams()

    gray = to_grayscale(image_bgr)

    # Normalização de intensidade: espalha o histograma para [0, 255],
    # compensando exposições sub/super-expostas entre capturas diferentes.
    normalized = cv2.normalize(gray, None, alpha=0, beta=255, norm_type=cv2.NORM_MINMAX)

    # Remoção de ruído: median blur (rápido, preserva bordas) seguido de
    # fastNlMeansDenoising (mais custoso, mas eficaz contra ruído granular
    # típico de sensores CMOS em baixa luminosidade de microscopia).
    ksize = params.median_blur_ksize if params.median_blur_ksize % 2 == 1 else params.median_blur_ksize + 1
    median_filtered = cv2.medianBlur(normalized, ksize)
    denoised = cv2.fastNlMeansDenoising(median_filtered, h=params.denoise_h)

    # CLAHE (Contrast Limited Adaptive Histogram Equalization): melhora o
    # contraste local sem saturar regiões já bem iluminadas, essencial para
    # destacar a borda de células pequenas e translúcidas.
    clahe = cv2.createCLAHE(
        clipLimit=params.clahe_clip_limit, tileGridSize=params.clahe_tile_grid_size
    )
    enhanced = clahe.apply(denoised)

    return enhanced
