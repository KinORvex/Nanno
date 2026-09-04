"""
Etapas 3 e 4 — Contagem total de células e distribuição de tamanhos.

Usa `skimage.measure.regionprops` sobre a matriz de rótulos gerada pelo
watershed para extrair, por célula: área, diâmetro equivalente, perímetro,
excentricidade e solidez. Regiões fora da faixa de área esperada ou com
formato muito irregular (baixa solidez) são descartadas como debris/artefatos
— Nannochloropsis é tipicamente esférica/ovalada, logo possui solidez alta.
"""
import statistics
from dataclasses import asdict, dataclass
from typing import List, Optional

import numpy as np
from skimage.measure import regionprops

from app.services.cell_analysis.config import CellDetectionParams


@dataclass(frozen=True)
class CellMeasurement:
    """Medidas de uma única célula detectada."""

    label_id: int
    centroid_x_px: float
    centroid_y_px: float
    area_px: float
    area_um2: float
    equivalent_diameter_um: float
    equivalent_radius_um: float
    perimeter_px: float
    eccentricity: float
    solidity: float

    def to_dict(self) -> dict:
        return asdict(self)


def extract_cell_measurements(
    labels: np.ndarray,
    params: CellDetectionParams = None,
) -> List[CellMeasurement]:
    """
    Converte a matriz de rótulos do watershed em uma lista de medições por
    célula, já filtrando por área e solidez para remover ruído/debris.
    """
    params = params or CellDetectionParams()
    scale = params.microns_per_pixel

    measurements: List[CellMeasurement] = []
    for region in regionprops(labels):
        if region.area < params.min_cell_area_px or region.area > params.max_cell_area_px:
            continue
        if region.solidity < params.min_solidity:
            continue

        centroid_y, centroid_x = region.centroid
        diameter_um = region.equivalent_diameter_area * scale if hasattr(
            region, "equivalent_diameter_area"
        ) else region.equivalent_diameter * scale

        measurements.append(
            CellMeasurement(
                label_id=int(region.label),
                centroid_x_px=float(centroid_x),
                centroid_y_px=float(centroid_y),
                area_px=float(region.area),
                area_um2=float(region.area * (scale**2)),
                equivalent_diameter_um=float(diameter_um),
                equivalent_radius_um=float(diameter_um / 2.0),
                perimeter_px=float(region.perimeter),
                eccentricity=float(region.eccentricity),
                solidity=float(region.solidity),
            )
        )
    return measurements


def _percentile(values: List[float], pct: float) -> Optional[float]:
    if not values:
        return None
    return float(np.percentile(values, pct))


def compute_summary_statistics(measurements: List[CellMeasurement]) -> dict:
    """
    Gera o resumo estatístico da distribuição de tamanhos a partir das
    medições individuais. Retorna um dicionário JSON-serializável, pronto
    para persistir em `MicroalgaeImage` / `extra_metrics`.
    """
    count = len(measurements)

    if count == 0:
        return {
            "cell_count": 0,
            "diameter_um": {"mean": None, "median": None, "std": None, "min": None, "max": None,
                             "p25": None, "p75": None},
            "area_um2": {"mean": None, "median": None, "std": None, "min": None, "max": None},
            "avg_confidence_score": None,
        }

    diameters = [m.equivalent_diameter_um for m in measurements]
    areas = [m.area_um2 for m in measurements]
    solidities = [m.solidity for m in measurements]

    # Usamos a solidez média como proxy de confiança da segmentação: células
    # bem separadas e redondas (alta solidez) indicam detecções confiáveis;
    # valores baixos sugerem fusões/oclusões parcialmente corrigidas pelo watershed.
    avg_confidence_score = float(statistics.fmean(solidities))

    return {
        "cell_count": count,
        "diameter_um": {
            "mean": float(statistics.fmean(diameters)),
            "median": float(statistics.median(diameters)),
            "std": float(statistics.pstdev(diameters)) if count > 1 else 0.0,
            "min": float(min(diameters)),
            "max": float(max(diameters)),
            "p25": _percentile(diameters, 25),
            "p75": _percentile(diameters, 75),
        },
        "area_um2": {
            "mean": float(statistics.fmean(areas)),
            "median": float(statistics.median(areas)),
            "std": float(statistics.pstdev(areas)) if count > 1 else 0.0,
            "min": float(min(areas)),
            "max": float(max(areas)),
        },
        "avg_confidence_score": avg_confidence_score,
    }


def estimate_cell_density(
    cell_count: int,
    image_area_um2: float,
    chamber_depth_um: float,
    dilution_factor: float = 1.0,
) -> Optional[float]:
    """
    Estima a densidade celular (células/mL) a partir da contagem em uma
    imagem, quando o volume de amostra imageado é conhecido — típico de
    câmaras de contagem tipo Neubauer/Sedgwick-Rafter adaptadas ao microscópio.

    volume_imageado_mL = (área_imagem_um2 * profundidade_câmara_um) * 1e-12
    (1 um3 = 1e-12 mL)

    Retorna None se os parâmetros de calibração forem inválidos (evita
    divisão por zero e densidades fisicamente sem sentido).
    """
    if image_area_um2 <= 0 or chamber_depth_um <= 0:
        return None

    volume_imaged_ml = (image_area_um2 * chamber_depth_um) * 1e-12
    if volume_imaged_ml <= 0:
        return None

    return (cell_count / volume_imaged_ml) * dilution_factor
