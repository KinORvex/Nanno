"""Testes unitários da heurística de crescimento (sem banco de dados)."""
from app.services.digital_twin.growth_heuristics import classify_growth_trend


def test_increasing_trend():
    assert classify_growth_trend([1000, 1100, 1300, 1600]) == "increasing"


def test_decreasing_trend():
    assert classify_growth_trend([1000, 900, 700, 500]) == "decreasing"


def test_stable_trend():
    assert classify_growth_trend([1000, 1020, 990, 1010]) == "stable"


def test_insufficient_data_returns_none():
    assert classify_growth_trend([1000]) is None
    assert classify_growth_trend([]) is None


def test_ignores_none_values():
    assert classify_growth_trend([None, 1000, None, 1300]) == "increasing"


def test_zero_first_value_returns_none():
    """Evita divisão por zero ao calcular variação percentual."""
    assert classify_growth_trend([0, 1000]) is None
