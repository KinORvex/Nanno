"""
Inferência: carrega um checkpoint treinado e gera a projeção de tendência
populacional a partir da janela mais recente de observações.

Usa MC-Dropout (múltiplas passagens estocásticas mantendo o dropout ativo)
para estimar um intervalo de confiança em torno da previsão pontual — uma
técnica leve que não exige reformular o modelo como probabilístico.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import numpy as np
import torch

from app.ml.config import DEFAULT_CHECKPOINT_PATH, FEATURE_COLUMNS, TARGET_COLUMN, ForecastModelConfig
from app.ml.dataset import FeatureScaler, InsufficientDataError, prepare_inference_window
from app.ml.model import build_model

logger = logging.getLogger(__name__)


class ModelNotTrainedError(Exception):
    """Nenhum checkpoint treinado foi encontrado no caminho esperado."""


@dataclass
class ForecastOutput:
    predicted_density: List[float]  # valores puntuais, um por dia do horizonte
    lower_bound: List[float]  # intervalo de confiança inferior (percentil 10)
    upper_bound: List[float]  # intervalo de confiança superior (percentil 90)
    trend_direction: str  # "increasing" | "decreasing" | "stable"
    percent_change: float  # variação percentual entre o início e o fim do horizonte

    def to_dict(self) -> dict:
        return {
            "predicted_density_cells_per_ml": self.predicted_density,
            "lower_bound_cells_per_ml": self.lower_bound,
            "upper_bound_cells_per_ml": self.upper_bound,
            "trend_direction": self.trend_direction,
            "percent_change": round(self.percent_change, 2),
        }


def load_checkpoint(
    path: Path = DEFAULT_CHECKPOINT_PATH, device: Optional[torch.device] = None
) -> tuple[torch.nn.Module, FeatureScaler, ForecastModelConfig]:
    """Carrega modelo + scaler + config de um checkpoint salvo por `train.save_checkpoint`."""
    device = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")

    if not path.exists():
        raise ModelNotTrainedError(
            f"Nenhum checkpoint encontrado em '{path}'. Treine o modelo antes de solicitar previsões "
            "(ver app.ml.train.train_model + save_checkpoint)."
        )

    # weights_only=False: o checkpoint contém, além dos tensores do modelo,
    # dicts simples (config e scaler). Seguro aqui porque `path` é sempre um
    # artefato gerado pelo nosso próprio `train.save_checkpoint` — NUNCA
    # aponte este loader para um arquivo de origem não confiável/externa.
    checkpoint = torch.load(path, map_location=device, weights_only=False)
    config = ForecastModelConfig(**checkpoint["config"])
    scaler = FeatureScaler.from_dict(checkpoint["scaler"])

    model = build_model(config).to(device)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()

    return model, scaler, config


def _enable_mc_dropout(model: torch.nn.Module) -> None:
    """
    Mantém apenas as camadas `nn.Dropout` explícitas em modo `train` (ativas),
    com o resto do modelo em modo `eval`.

    Nota: o dropout interno de `nn.LSTM` (entre camadas recorrentes) é
    implementado internamente pelo backend e não é exposto como um submódulo
    `nn.Dropout` — portanto o MC-Dropout aqui perturba apenas a cabeça (head)
    do modelo, não as camadas recorrentes. Isso ainda produz uma estimativa
    de incerteza útil, mas mais conservadora do que perturbar a rede inteira.
    """
    for module in model.modules():
        if isinstance(module, torch.nn.Dropout):
            module.train()


def predict_trend(
    model: torch.nn.Module,
    scaler: FeatureScaler,
    config: ForecastModelConfig,
    feature_matrix: np.ndarray,
    device: Optional[torch.device] = None,
    stability_threshold_pct: float = 5.0,
) -> ForecastOutput:
    """
    Gera a previsão de densidade celular para os próximos `config.forecast_horizon`
    dias, a partir da janela mais recente de `feature_matrix`.

    Args:
        feature_matrix: histórico completo (n_steps, n_features), já
            interpolado (ver `dataset.build_feature_matrix`). Apenas a
            última `config.input_window` é efetivamente usada.
        stability_threshold_pct: variação percentual abaixo da qual a
            tendência é classificada como "stable" em vez de crescente/decrescente.

    Raises:
        InsufficientDataError: histórico menor que `config.input_window`.
    """
    device = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")
    target_index = FEATURE_COLUMNS.index(TARGET_COLUMN)

    window = prepare_inference_window(feature_matrix, config.input_window, scaler)
    x = torch.from_numpy(window).float().unsqueeze(0).to(device)  # (1, input_window, n_features)

    model.eval()
    _enable_mc_dropout(model)

    samples = []
    with torch.no_grad():
        for _ in range(config.mc_dropout_samples):
            pred_scaled = model(x).squeeze(0).cpu().numpy()  # (forecast_horizon,)
            pred = scaler.inverse_transform_target(pred_scaled, target_index)
            samples.append(pred)

    samples_array = np.stack(samples)  # (mc_samples, forecast_horizon)
    point_estimate = samples_array.mean(axis=0)
    lower_bound = np.percentile(samples_array, 10, axis=0)
    upper_bound = np.percentile(samples_array, 90, axis=0)

    # Densidade não pode ser negativa — trunca o intervalo inferior.
    lower_bound = np.clip(lower_bound, a_min=0, a_max=None)

    current_density = feature_matrix[-1, target_index]
    final_predicted = point_estimate[-1]
    percent_change = (
        ((final_predicted - current_density) / current_density) * 100.0 if current_density > 0 else 0.0
    )

    if abs(percent_change) < stability_threshold_pct:
        direction = "stable"
    elif percent_change > 0:
        direction = "increasing"
    else:
        direction = "decreasing"

    return ForecastOutput(
        predicted_density=point_estimate.tolist(),
        lower_bound=lower_bound.tolist(),
        upper_bound=upper_bound.tolist(),
        trend_direction=direction,
        percent_change=float(percent_change),
    )


class ForecastModelRegistry:
    """
    Singleton leve que mantém o modelo carregado em memória entre
    requisições — carregar pesos do disco a cada chamada de API seria caro
    e desnecessário, já que o checkpoint só muda quando um retrain roda.
    """

    _instance: Optional["ForecastModelRegistry"] = None

    def __init__(self, checkpoint_path: Path = DEFAULT_CHECKPOINT_PATH):
        self.checkpoint_path = checkpoint_path
        self._model = None
        self._scaler = None
        self._config = None

    @classmethod
    def get_instance(cls) -> "ForecastModelRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _ensure_loaded(self) -> None:
        if self._model is None:
            self._model, self._scaler, self._config = load_checkpoint(self.checkpoint_path)

    def reload(self) -> None:
        """Força o recarregamento do checkpoint (chamar após um novo treino)."""
        self._model = None
        self._ensure_loaded()

    def predict(self, feature_matrix: np.ndarray, **kwargs) -> ForecastOutput:
        self._ensure_loaded()
        return predict_trend(self._model, self._scaler, self._config, feature_matrix, **kwargs)

    @property
    def config(self) -> ForecastModelConfig:
        self._ensure_loaded()
        return self._config
