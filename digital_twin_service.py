"""
Orquestra o cálculo do estado do Gêmeo Digital de uma Culture: reúne
métricas observadas, aplica a heurística de crescimento e o serviço de
avaliação de estresse, e persiste um novo snapshot (DigitalTwinState).

Fluxo (conforme especificado):
    Culture -> Observations -> Metrics -> Environmental Data -> Digital Twin State

Esta é a primeira versão (v1): NÃO usa LSTM/rede neural. O módulo de
previsão mais robusto (`app/ml/`) permanece disponível para evolução
futura, quando o volume de dados por cultura justificar seu uso.
"""
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.culture import Culture
from app.models.digital_twin import DigitalTwinState
from app.models.observation import Observation
from app.services.digital_twin.growth_heuristics import classify_growth_trend
from app.services.digital_twin.stress_assessment import assess_culture_stress


def _latest_environmental_snapshot(observations: List[Observation]) -> Optional[dict]:
    for obs in reversed(observations):
        reading = obs.environmental_reading
        if reading is not None:
            return {
                "temperature_c": reading.temperature_c,
                "ph": reading.ph,
                "salinity_psu": reading.salinity_psu,
                "light_intensity_umol_m2_s": reading.light_intensity_umol_m2_s,
                "dissolved_oxygen_mg_l": reading.dissolved_oxygen_mg_l,
                "recorded_at": reading.recorded_at.isoformat() if reading.recorded_at else None,
            }
    return None


def _latest_metrics_per_observation(observations: List[Observation]) -> List[Optional[dict]]:
    """Para cada observação, retorna o dict de métricas da análise mais
    recente associada a ela (ou None se não houver análise concluída)."""
    result = []
    for obs in observations:
        analyses = [a for a in obs.analyses if a.metrics]
        result.append(max(analyses, key=lambda a: a.created_at).metrics if analyses else None)
    return result


def compute_digital_twin_state(db: Session, culture: Culture, persist: bool = True) -> DigitalTwinState:
    """
    Calcula (e, por padrão, persiste) um novo snapshot do estado do gêmeo
    digital de `culture`. Todos os campos ficam None/UNKNOWN quando não há
    dados suficientes para uma estimativa cientificamente justificável —
    nenhum valor é inventado.
    """
    observations = sorted(culture.observations, key=lambda o: o.observed_at)
    metrics_per_obs = _latest_metrics_per_observation(observations)

    cell_counts = [m.get("cell_count") if m else None for m in metrics_per_obs]
    growth_state = classify_growth_trend(cell_counts)

    latest_metrics = next((m for m in reversed(metrics_per_obs) if m is not None), None)

    stress_result = assess_culture_stress(db, culture)

    density_estimate = latest_metrics.get("cell_density_cells_per_ml") if latest_metrics else None
    morphological_state = (
        {
            "diameter_mean_um": latest_metrics.get("diameter_mean_um"),
            "diameter_cv": latest_metrics.get("diameter_cv"),
            "cell_count": latest_metrics.get("cell_count"),
        }
        if latest_metrics
        else None
    )

    state = DigitalTwinState(
        culture_id=culture.id,
        based_on_observation_id=observations[-1].id if observations else None,
        computed_at=datetime.now(timezone.utc),
        # biomass_estimate: sem uma calibração massa/célula validada ainda —
        # deliberadamente None em vez de um valor inventado (ver item 7 do escopo).
        biomass_estimate=None,
        density_estimate=density_estimate,
        morphological_state=morphological_state,
        environmental_state=_latest_environmental_snapshot(observations),
        growth_state=growth_state,
        health_status=stress_result.health_status,
        stress_score=stress_result.stress_score,
        confidence=stress_result.confidence,
        contributing_factors=stress_result.contributing_factors or None,
    )

    if persist:
        db.add(state)
        db.commit()
        db.refresh(state)

    return state
