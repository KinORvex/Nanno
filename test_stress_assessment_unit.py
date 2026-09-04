"""
Testes unitários puros do serviço de avaliação de estresse — não requerem
banco de dados, apenas objetos com os atributos esperados (duck typing).

Esta lógica foi validada manualmente durante o desenvolvimento com stubs
equivalentes antes de este arquivo existir; os casos abaixo espelham
exatamente os cenários já comprovados, incluindo a regressão do bug
encontrado (cell_count causando falso positivo).
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from app.models.digital_twin import HealthStatus
from app.services.digital_twin.stress_assessment import assess_culture_stress


@dataclass
class FakeAnalysis:
    metrics: dict
    created_at: datetime


@dataclass
class FakeObservation:
    observed_at: datetime
    analyses: List[FakeAnalysis]


@dataclass
class FakeCulture:
    observations: List[FakeObservation]
    stress_induced_at: Optional[datetime] = None


def _make_obs(day, diameter, cell_count):
    t = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=day)
    analysis = FakeAnalysis(
        metrics={"diameter_mean_um": diameter, "diameter_cv": 0.15, "cell_count": cell_count}, created_at=t
    )
    return FakeObservation(observed_at=t, analyses=[analysis])


def test_insufficient_history_returns_unknown():
    culture = FakeCulture(observations=[_make_obs(0, 3.0, 1000)])
    result = assess_culture_stress(None, culture)
    assert result.health_status == HealthStatus.UNKNOWN
    assert result.stress_score is None
    assert result.confidence is None


def test_healthy_growth_does_not_trigger_false_positive():
    """Regressão do bug encontrado durante o desenvolvimento: cell_count
    crescendo normalmente não deve, por si só, disparar WARNING/STRESSED."""
    diameters = [3.00, 3.04, 2.97, 3.02, 3.01, 2.99]
    obs = [_make_obs(d, diameters[d], 1000 + d * 50) for d in range(6)]
    culture = FakeCulture(observations=obs, stress_induced_at=None)
    result = assess_culture_stress(None, culture)
    assert result.health_status == HealthStatus.NORMAL


def test_real_stress_signal_is_detected():
    tstress = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=4)
    baseline_diameters = [3.00, 3.04, 2.97, 3.02]
    baseline = [_make_obs(d, baseline_diameters[d], 1000 + d * 100) for d in range(4)]
    stressed = [_make_obs(d, 3.9, 1000 + d * 20) for d in range(4, 8)]
    culture = FakeCulture(observations=baseline + stressed, stress_induced_at=tstress)
    result = assess_culture_stress(None, culture)
    assert result.health_status == HealthStatus.STRESSED
    assert "diameter_mean_um" in result.contributing_factors


def test_zero_variance_baseline_is_handled_safely():
    """Baseline sem nenhuma variação (incomum em dado real, mas não deve
    lançar exceção nem gerar z-score infinito/indefinido)."""
    obs = [_make_obs(d, 3.0, 1000) for d in range(5)]
    culture = FakeCulture(observations=obs, stress_induced_at=None)
    result = assess_culture_stress(None, culture)
    assert result.health_status in (HealthStatus.UNKNOWN, HealthStatus.NORMAL)


def test_missing_metrics_returns_unknown_not_error():
    """Observações sem nenhuma análise associada (upload falhou, por
    exemplo) não devem quebrar o serviço."""
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    obs = [FakeObservation(observed_at=t + timedelta(days=d), analyses=[]) for d in range(5)]
    culture = FakeCulture(observations=obs)
    result = assess_culture_stress(None, culture)
    assert result.health_status == HealthStatus.UNKNOWN
    assert result.message is not None
