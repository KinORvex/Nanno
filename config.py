"""
Parâmetros configuráveis do pipeline de detecção de células.

Os valores padrão foram calibrados para células de Nannochloropsis (esféricas/
ovais, ~2-5 µm de diâmetro) em imagens de microscopia óptica de campo claro ou
contraste de fase, mas devem ser ajustados por objetiva/câmera do laboratório.
"""
from dataclasses import dataclass, field
from typing import Literal, Tuple


@dataclass(frozen=True)
class CellDetectionParams:
    # --- Calibração óptica (OBRIGATÓRIO ajustar por microscópio/objetiva) ---
    # Quantos micrômetros cada pixel representa. Obtido calibrando com uma
    # lâmina micrométrica ou a partir da especificação da câmera/objetiva.
    microns_per_pixel: float = 0.1

    # --- Pré-processamento ---
    clahe_clip_limit: float = 2.0
    clahe_tile_grid_size: Tuple[int, int] = (8, 8)
    denoise_h: float = 7.0  # força do fastNlMeansDenoising (maior = mais suave)
    median_blur_ksize: int = 3  # deve ser ímpar

    # --- Segmentação ---
    threshold_method: Literal["otsu", "adaptive"] = "otsu"
    adaptive_block_size: int = 51  # deve ser ímpar
    adaptive_c: float = -3.0
    # Se True, assume células mais escuras que o fundo (campo claro típico);
    # se False, assume células mais claras que o fundo (contraste de fase/fluorescência).
    cells_darker_than_background: bool = True

    morph_kernel_size: int = 3
    morph_open_iterations: int = 1
    morph_close_iterations: int = 2

    # Distância mínima (em pixels) entre picos locais no watershed — evita
    # que uma única célula grande seja fragmentada em múltiplos rótulos.
    watershed_min_distance: int = 7

    # --- Filtragem de artefatos/debris pós-segmentação ---
    min_cell_area_px: int = 15
    max_cell_area_px: int = 5000
    # Solidez mínima (área/área do casco convexo). Nannochloropsis é
    # arredondada, então debris irregulares (solidez baixa) são descartados.
    min_solidity: float = 0.80

    # --- Visualização ---
    annotation_circle_color_bgr: Tuple[int, int, int] = (0, 255, 0)
    annotation_circle_thickness: int = 1
    annotation_font_scale: float = 0.6


DEFAULT_PARAMS = CellDetectionParams()
