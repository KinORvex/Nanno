"""
Heurística simples (SEM machine learning) para classificar a tendência de
crescimento recente de uma cultura — o módulo de "previsão leve" do gêmeo
digital nesta primeira versão.

Modelos mais sofisticados (regressão, séries temporais, LSTM) permanecem em
`app/ml/`, reservados para quando o volume de dados por cultura justificar
seu uso — não são acionados por esta primeira versão do Digital Twin,
conforme explicitamente solicitado.
"""
from typing import List, Optional

STABLE_THRESHOLD_PCT = 5.0


def classify_growth_trend(cell_counts: List[Optional[float]]) -> Optional[str]:
    """
    Classifica a tendência de crescimento comparando o primeiro e o último
    valor válido de uma série de contagens de células (ordenada
    cronologicamente). Retorna None (não "stable") se não houver dados
    suficientes — nunca inventa uma tendência sem base.
    """
    valid_counts = [c for c in cell_counts if c is not None]
    if len(valid_counts) < 2:
        return None

    first, last = valid_counts[0], valid_counts[-1]
    if first <= 0:
        return None

    percent_change = ((last - first) / first) * 100.0
    if abs(percent_change) < STABLE_THRESHOLD_PCT:
        return "stable"
    return "increasing" if percent_change > 0 else "decreasing"
