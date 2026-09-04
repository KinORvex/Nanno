"""
Preparação de dados para o modelo de previsão de tendência populacional.

Este módulo é dividido em duas partes:
1. Funções puras em NumPy (engenharia de features, normalização, janelamento)
   — sem dependência de PyTorch, fáceis de testar isoladamente.
2. `SequenceDataset`, um `torch.utils.data.Dataset` fino que apenas empacota
   os arrays já preparados em tensores para o treinamento.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np

from app.ml.config import FEATURE_COLUMNS, TARGET_COLUMN, ForecastModelConfig


class InsufficientDataError(Exception):
    """Não há observações suficientes para formar ao menos uma janela de treino/inferência."""


@dataclass
class FeatureScaler:
    """
    Normalizador z-score (média/desvio padrão) por coluna, calculado no
    conjunto de treino e reaplicado — com os mesmos parâmetros — no
    conjunto de validação e na inferência. Evita vazamento de dados (data
    leakage) e garante que a escala usada para desnormalizar a previsão
    seja exatamente a do treino.
    """

    mean: np.ndarray
    std: np.ndarray

    def transform(self, x: np.ndarray) -> np.ndarray:
        return (x - self.mean) / self.std

    def inverse_transform_target(self, y: np.ndarray, target_index: int) -> np.ndarray:
        return y * self.std[target_index] + self.mean[target_index]

    def to_dict(self) -> dict:
        return {"mean": self.mean.tolist(), "std": self.std.tolist()}

    @classmethod
    def from_dict(cls, data: dict) -> "FeatureScaler":
        return cls(mean=np.array(data["mean"], dtype=np.float32), std=np.array(data["std"], dtype=np.float32))

    @classmethod
    def fit(cls, x: np.ndarray) -> "FeatureScaler":
        mean = x.mean(axis=0)
        std = x.std(axis=0)
        std[std < 1e-6] = 1e-6  # evita divisão por zero em features constantes
        return cls(mean=mean.astype(np.float32), std=std.astype(np.float32))


def interpolate_missing(feature_matrix: np.ndarray) -> np.ndarray:
    """
    Preenche valores ausentes (NaN) por coluna via interpolação linear no
    tempo, com preenchimento por vizinho mais próximo nas bordas. Leituras
    ambientais costumam ser esparsas (nem toda imagem tem uma leitura de
    sensor no mesmo instante) — descartar linhas com NaN destruiria a
    continuidade temporal necessária para o LSTM.
    """
    result = feature_matrix.copy()
    n_steps, n_features = result.shape
    x = np.arange(n_steps)

    for col in range(n_features):
        col_values = result[:, col]
        valid = ~np.isnan(col_values)

        if valid.sum() == 0:
            # Nenhuma leitura para esta feature em toda a série — impossível
            # interpolar; preenche com zero (a normalização depois torna
            # isso neutro em relação à média da própria coluna, se ela for
            # constante em zero durante o fit do scaler).
            result[:, col] = 0.0
            continue
        if valid.sum() < n_steps:
            result[:, col] = np.interp(x, x[valid], col_values[valid])

    return result


def build_feature_matrix(
    records: Sequence[dict],
    feature_columns: List[str] = FEATURE_COLUMNS,
) -> np.ndarray:
    """
    Converte uma sequência de dicionários (uma linha por timestamp, já
    ordenada cronologicamente) na matriz (n_steps, n_features) esperada pelo
    modelo, interpolando valores ausentes.

    `records` normalmente vem de uma junção entre `MicroalgaeImage` e
    `EnvironmentalReading` por proximidade temporal (ver `api/v1/endpoints/forecast.py`).
    """
    if not records:
        raise InsufficientDataError("Nenhum registro histórico disponível.")

    raw = np.array(
        [[float(r[col]) if r.get(col) is not None else np.nan for col in feature_columns] for r in records],
        dtype=np.float32,
    )
    return interpolate_missing(raw)


def create_sliding_windows(
    feature_matrix: np.ndarray,
    input_window: int,
    forecast_horizon: int,
    target_index: int,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Gera pares (X, y) por janela deslizante:
        X[i] = feature_matrix[i : i+input_window]                       -> (input_window, n_features)
        y[i] = feature_matrix[i+input_window : i+input_window+horizon, target_index] -> (horizon,)

    Retorna arrays (n_windows, input_window, n_features) e (n_windows, horizon).
    """
    n_steps = feature_matrix.shape[0]
    n_windows = n_steps - input_window - forecast_horizon + 1

    if n_windows <= 0:
        raise InsufficientDataError(
            f"Histórico insuficiente: {n_steps} observações, mas são necessárias "
            f"pelo menos {input_window + forecast_horizon} (input_window={input_window} "
            f"+ forecast_horizon={forecast_horizon})."
        )

    X = np.stack([feature_matrix[i : i + input_window] for i in range(n_windows)])
    y = np.stack(
        [
            feature_matrix[i + input_window : i + input_window + forecast_horizon, target_index]
            for i in range(n_windows)
        ]
    )
    return X.astype(np.float32), y.astype(np.float32)


def prepare_inference_window(
    feature_matrix: np.ndarray, input_window: int, scaler: FeatureScaler
) -> np.ndarray:
    """
    Extrai e normaliza a última janela disponível da série (as `input_window`
    observações mais recentes), pronta para ser convertida em tensor e
    passada ao modelo treinado.
    """
    if feature_matrix.shape[0] < input_window:
        raise InsufficientDataError(
            f"São necessárias ao menos {input_window} observações para prever "
            f"a tendência; há apenas {feature_matrix.shape[0]}."
        )
    last_window = feature_matrix[-input_window:]
    return scaler.transform(last_window)


def train_val_split(
    X: np.ndarray, y: np.ndarray, val_split: float, random_seed: int
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Split treino/validação respeitando a ordem temporal: as janelas mais
    recentes formam a validação (evita usar o futuro para "prever o passado"
    durante a avaliação, o que aconteceria com um shuffle aleatório).
    """
    n = X.shape[0]
    n_val = max(1, int(round(n * val_split))) if n > 1 else 0
    n_train = n - n_val

    if n_train < 1:
        # Série muito curta para separar validação — usa tudo para treino.
        return X, y, X[:0], y[:0]

    return X[:n_train], y[:n_train], X[n_train:], y[n_train:]


# --------------------------------------------------------------------------- #
# Wrapper torch — mantido no final do arquivo e só importado quando o
# treinamento/inferência de fato precisa de tensores (mantém as funções
# acima testáveis sem exigir PyTorch instalado).
# --------------------------------------------------------------------------- #
import torch  # noqa: E402
from torch.utils.data import Dataset  # noqa: E402


class SequenceDataset(Dataset):
    """Empacota janelas (X, y) já normalizadas em `torch.Tensor` para o `DataLoader`."""

    def __init__(self, X: np.ndarray, y: np.ndarray):
        self.X = torch.from_numpy(X).float()
        self.y = torch.from_numpy(y).float()

    def __len__(self) -> int:
        return self.X.shape[0]

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        return self.X[idx], self.y[idx]
