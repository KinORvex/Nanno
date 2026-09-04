"""
Serviço de avaliação de estresse (v1, SEM machine learning).

Implementa exatamente o mecanismo definido no plano de pesquisa aprovado:
compara a(s) observação(ões) mais recente(s) de uma Culture contra a
"assinatura basal" daquela mesma cultura — média/desvio-padrão das
observações anteriores ao início do estresse (`culture.stress_induced_at`),
ou de todo o histórico exceto a última observação, se nenhum marco de
estresse tiver sido definido — expressando o desvio em unidades de
desvio-padrão (z-score).

Deliberadamente NÃO usa aprendizado de máquina nesta versão: com poucas
observações por cultura, um modelo treinado não seria cientificamente
defensável (mesmo raciocínio já aplicado aos modelos de crescimento em
`app/ml`). A complexidade deve crescer apenas se o volume de dados
justificar — este serviço é o "Nível 1 + Nível 2" descritos no plano de
pesquisa (z-score univariado -> escore composto simples).
"""
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.culture import Culture
from app.models.digital_twin import HealthStatus
from app.models.observation import Observation

# Métricas avaliadas para o escore de estresse (z-score vs. assinatura
# basal ESTÁTICA). Deliberadamente NÃO inclui `cell_count`: contagem de
# células cresce de forma esperada mesmo numa cultura saudável, então
# compará-la contra uma média basal estática geraria falsos positivos
# sistemáticos durante crescimento normal (confirmado em teste). A tendência
# de crescimento é avaliada separadamente, de forma sensível a tendência
# (não a um baseline fixo), por `growth_heuristics.classify_growth_trend`.
EVALUATED_METRICS = ["diameter_mean_um", "diameter_cv"]

MIN_BASELINE_OBSERVATIONS = 3  # mínimo para estimar desvio-padrão de forma minimamente informativa
WARNING_Z_THRESHOLD = 1.0
STRESSED_Z_THRESHOLD = 2.0
CONSECUTIVE_REQUIRED = 2  # nº de observações consecutivas acima do limiar para confirmar STRESSED


@dataclass
class StressAssessmentResult:
    health_status: HealthStatus
    stress_score: Optional[float]
    confidence: Optional[float]
    contributing_factors: Dict[str, float] = field(default_factory=dict)
    message: Optional[str] = None


def _extract_metric_series(observations: List[Observation], metric_key: str) -> List[float]:
    """Extrai uma métrica das análises de imagem associadas a cada observação,
    usando a análise mais recente por observação quando há mais de uma imagem."""
    values = []
    for obs in observations:
        analyses = [
            a for a in obs.analyses
            if a.metrics and metric_key in a.metrics and a.metrics[metric_key] is not None
        ]
        if not analyses:
            continue
        latest = max(analyses, key=lambda a: a.created_at)
        values.append(latest.metrics[metric_key])
    return values


def _zscore(value: float, baseline_values: List[float]) -> Optional[float]:
    if len(baseline_values) < MIN_BASELINE_OBSERVATIONS:
        return None
    mean = statistics.fmean(baseline_values)
    std = statistics.pstdev(baseline_values)
    if std < 1e-9:
        return None  # baseline sem variância — z-score não é informativo
    return (value - mean) / std


def assess_culture_stress(db: Session, culture: Culture) -> StressAssessmentResult:
    """
    Calcula o estado de estresse da cultura a partir da assinatura basal.

    NUNCA inventa um valor: se não há observações/métricas suficientes,
    retorna HealthStatus.UNKNOWN com stress_score/confidence = None e uma
    mensagem explicando o motivo.
    """
    all_observations = sorted(culture.observations, key=lambda o: o.observed_at)

    if len(all_observations) < MIN_BASELINE_OBSERVATIONS + 1:
        return StressAssessmentResult(
            health_status=HealthStatus.UNKNOWN,
            stress_score=None,
            confidence=None,
            message=(
                f"Histórico insuficiente: {len(all_observations)} observação(ões), "
                f"são necessárias ao menos {MIN_BASELINE_OBSERVATIONS + 1} "
                "(linha de base + ao menos 1 observação avaliada)."
            ),
        )

    if culture.stress_induced_at is not None:
        baseline_obs = [o for o in all_observations if o.observed_at < culture.stress_induced_at]
        evaluated_obs = [o for o in all_observations if o.observed_at >= culture.stress_induced_at]
    else:
        baseline_obs = all_observations[:-1]
        evaluated_obs = all_observations[-1:]

    if len(baseline_obs) < MIN_BASELINE_OBSERVATIONS or not evaluated_obs:
        return StressAssessmentResult(
            health_status=HealthStatus.UNKNOWN,
            stress_score=None,
            confidence=None,
            message="Linha de base insuficiente para calcular assinatura basal confiável.",
        )

    # Avalia as últimas CONSECUTIVE_REQUIRED observações, para decidir
    # STRESSED de forma robusta a ruído de uma única medição isolada.
    recent_obs = evaluated_obs[-CONSECUTIVE_REQUIRED:]

    per_observation_composites: List[float] = []
    last_contributing_factors: Dict[str, float] = {}

    for obs in recent_obs:
        z_scores: Dict[str, float] = {}
        for metric_key in EVALUATED_METRICS:
            baseline_values = _extract_metric_series(baseline_obs, metric_key)
            current_values = _extract_metric_series([obs], metric_key)
            if not current_values:
                continue
            z = _zscore(current_values[0], baseline_values)
            if z is not None:
                z_scores[metric_key] = z

        if not z_scores:
            continue

        composite = statistics.fmean(abs(z) for z in z_scores.values())
        per_observation_composites.append(composite)
        last_contributing_factors = z_scores

    if not per_observation_composites:
        return StressAssessmentResult(
            health_status=HealthStatus.UNKNOWN,
            stress_score=None,
            confidence=None,
            message="Nenhuma métrica avaliável nas observações recentes (análises de imagem ausentes).",
        )

    latest_composite = per_observation_composites[-1]
    sustained = (
        len(per_observation_composites) >= CONSECUTIVE_REQUIRED
        and all(c >= STRESSED_Z_THRESHOLD for c in per_observation_composites)
    )

    if sustained:
        health_status = HealthStatus.STRESSED
    elif latest_composite >= WARNING_Z_THRESHOLD:
        health_status = HealthStatus.WARNING
    else:
        health_status = HealthStatus.NORMAL

    # Confiança cresce com o tamanho da linha de base (mais robusta a
    # ruído), truncada em 0.95 — nunca alegamos certeza total.
    confidence = min(0.95, len(baseline_obs) / (MIN_BASELINE_OBSERVATIONS * 3))

    return StressAssessmentResult(
        health_status=health_status,
        stress_score=round(latest_composite, 3),
        confidence=round(confidence, 3),
        contributing_factors={k: round(v, 3) for k, v in last_contributing_factors.items()},
    )
