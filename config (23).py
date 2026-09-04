"""Configuração do pipeline de forecasting: hiperparâmetros do modelo,
features utilizadas e caminhos de artefatos treinados."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

# Ordem fixa das features — usada tanto no treino quanto na inferência.
# Mudar esta lista invalida checkpoints já treinados (o input_size do
# modelo depende diretamente do tamanho dela).
FEATURE_COLUMNS: List[str] = [
    "cell_density_cells_per_ml",
    "avg_cell_diameter_um",
    "temperature_c",
    "ph",
    "light_intensity_umol_m2_s",
]
TARGET_COLUMN = "cell_density_cells_per_ml"

ARTIFACTS_DIR = Path(__file__).parent / "artifacts"
DEFAULT_CHECKPOINT_PATH = ARTIFACTS_DIR / "nanno_forecaster.pt"


@dataclass(frozen=True)
class ForecastModelConfig:
    # --- Arquitetura ---
    architecture: str = "lstm"  # "lstm" ou "mlp"
    input_size: int = len(FEATURE_COLUMNS)
    hidden_size: int = 64
    num_layers: int = 2
    dropout: float = 0.2

    # --- Janela temporal ---
    # Nº de observações históricas usadas para prever o futuro, e nº de
    # passos futuros previstos de uma vez (horizonte de previsão).
    input_window: int = 14
    forecast_horizon: int = 7

    # --- Treinamento ---
    batch_size: int = 16
    learning_rate: float = 1e-3
    weight_decay: float = 1e-5
    max_epochs: int = 200
    early_stopping_patience: int = 15
    val_split: float = 0.2
    grad_clip_norm: float = 1.0
    random_seed: int = 42

    # --- Inferência ---
    # Nº de passagens estocásticas (MC-Dropout) para estimar incerteza da previsão.
    mc_dropout_samples: int = 30


DEFAULT_CONFIG = ForecastModelConfig()
