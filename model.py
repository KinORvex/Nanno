"""
Arquiteturas de modelo para previsão de densidade populacional de
Nannochloropsis a partir de histórico de contagens de células + dados
ambientais.

Duas arquiteturas são oferecidas:
- `LSTMForecaster` (padrão): captura dependências temporais de médio prazo
  entre observações — melhor quando há histórico razoavelmente longo
  (semanas de dados).
- `MLPForecaster`: baseline mais simples que achata a janela temporal em um
  único vetor; útil como fallback quando o histórico é curto demais para o
  LSTM generalizar bem, ou como comparação de sanidade durante o desenvolvimento.
"""
from __future__ import annotations

import torch
import torch.nn as nn

from app.ml.config import ForecastModelConfig


class LSTMForecaster(nn.Module):
    """
    Recebe uma sequência (batch, input_window, input_size) com o histórico de
    [densidade celular, diâmetro médio, temperatura, pH, luminosidade] e
    prevê os próximos `forecast_horizon` valores de densidade celular.
    """

    def __init__(self, config: ForecastModelConfig):
        super().__init__()
        self.config = config

        self.lstm = nn.LSTM(
            input_size=config.input_size,
            hidden_size=config.hidden_size,
            num_layers=config.num_layers,
            batch_first=True,
            dropout=config.dropout if config.num_layers > 1 else 0.0,
        )

        # Dropout explícito aplicado à última hidden state — permanece ativo
        # durante a inferência com MC-Dropout para estimar incerteza (ver inference.py).
        self.head_dropout = nn.Dropout(config.dropout)
        self.head = nn.Sequential(
            nn.Linear(config.hidden_size, config.hidden_size // 2),
            nn.ReLU(),
            nn.Dropout(config.dropout),
            nn.Linear(config.hidden_size // 2, config.forecast_horizon),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (batch, input_window, input_size)
        _output, (h_n, _c_n) = self.lstm(x)
        # h_n: (num_layers, batch, hidden_size) — pegamos o estado oculto
        # final da última camada, que resume toda a sequência de entrada.
        last_hidden = h_n[-1]  # (batch, hidden_size)
        last_hidden = self.head_dropout(last_hidden)
        return self.head(last_hidden)  # (batch, forecast_horizon)


class MLPForecaster(nn.Module):
    """
    Baseline simples: achata a janela temporal (input_window * input_size)
    e usa um MLP totalmente conectado. Não modela explicitamente a ordem
    temporal — serve como piso de comparação e alternativa leve quando o
    histórico é curto demais para justificar um LSTM.
    """

    def __init__(self, config: ForecastModelConfig):
        super().__init__()
        self.config = config
        flat_size = config.input_window * config.input_size

        self.net = nn.Sequential(
            nn.Linear(flat_size, config.hidden_size),
            nn.ReLU(),
            nn.Dropout(config.dropout),
            nn.Linear(config.hidden_size, config.hidden_size // 2),
            nn.ReLU(),
            nn.Dropout(config.dropout),
            nn.Linear(config.hidden_size // 2, config.forecast_horizon),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (batch, input_window, input_size) -> (batch, input_window * input_size)
        batch_size = x.shape[0]
        flattened = x.reshape(batch_size, -1)
        return self.net(flattened)


def build_model(config: ForecastModelConfig) -> nn.Module:
    """Fábrica: instancia a arquitetura indicada em `config.architecture`."""
    if config.architecture == "lstm":
        return LSTMForecaster(config)
    if config.architecture == "mlp":
        return MLPForecaster(config)
    raise ValueError(f"Arquitetura desconhecida: '{config.architecture}' (use 'lstm' ou 'mlp').")
