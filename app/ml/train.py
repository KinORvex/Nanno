"""Funções de treinamento do modelo de previsão de tendência populacional."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from app.ml.config import DEFAULT_CHECKPOINT_PATH, FEATURE_COLUMNS, TARGET_COLUMN, ForecastModelConfig
from app.ml.dataset import FeatureScaler, SequenceDataset, create_sliding_windows, train_val_split
from app.ml.model import build_model

logger = logging.getLogger(__name__)


@dataclass
class TrainingHistory:
    train_loss: List[float] = field(default_factory=list)
    val_loss: List[float] = field(default_factory=list)
    best_epoch: int = 0
    best_val_loss: float = float("inf")
    stopped_early: bool = False


def _run_epoch(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
    optimizer: Optional[torch.optim.Optimizer] = None,
    grad_clip_norm: Optional[float] = None,
) -> float:
    """Executa uma época de treino (se `optimizer` for passado) ou avaliação."""
    is_training = optimizer is not None
    model.train(is_training)

    total_loss = 0.0
    n_batches = 0

    context = torch.enable_grad() if is_training else torch.no_grad()
    with context:
        for X_batch, y_batch in loader:
            X_batch, y_batch = X_batch.to(device), y_batch.to(device)

            if is_training:
                optimizer.zero_grad()

            predictions = model(X_batch)
            loss = criterion(predictions, y_batch)

            if is_training:
                loss.backward()
                if grad_clip_norm:
                    nn.utils.clip_grad_norm_(model.parameters(), grad_clip_norm)
                optimizer.step()

            total_loss += loss.item()
            n_batches += 1

    return total_loss / max(1, n_batches)


def train_model(
    feature_matrix: np.ndarray,
    config: ForecastModelConfig,
    device: Optional[torch.device] = None,
) -> tuple[nn.Module, FeatureScaler, TrainingHistory]:
    """
    Treina o modelo de previsão a partir de uma matriz de features já
    interpolada (ver `dataset.build_feature_matrix`), com early stopping
    baseado na perda de validação.

    Retorna o modelo com os MELHORES pesos observados (não necessariamente
    os da última época), o scaler ajustado no treino, e o histórico de perdas.
    """
    device = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")
    torch.manual_seed(config.random_seed)

    target_index = FEATURE_COLUMNS.index(TARGET_COLUMN)
    X, y = create_sliding_windows(
        feature_matrix,
        input_window=config.input_window,
        forecast_horizon=config.forecast_horizon,
        target_index=target_index,
    )

    X_train, y_train, X_val, y_val = train_val_split(X, y, config.val_split, config.random_seed)

    # O scaler é ajustado APENAS nas janelas de treino, para não vazar
    # estatísticas do conjunto de validação (nem, futuramente, de produção).
    scaler = FeatureScaler.fit(X_train.reshape(-1, X_train.shape[-1]))
    X_train = scaler.transform(X_train.reshape(-1, X_train.shape[-1])).reshape(X_train.shape)
    y_train_scaled = (y_train - scaler.mean[target_index]) / scaler.std[target_index]

    has_val = X_val.shape[0] > 0
    if has_val:
        X_val = scaler.transform(X_val.reshape(-1, X_val.shape[-1])).reshape(X_val.shape)
        y_val_scaled = (y_val - scaler.mean[target_index]) / scaler.std[target_index]

    train_loader = DataLoader(
        SequenceDataset(X_train, y_train_scaled),
        batch_size=min(config.batch_size, len(X_train)),
        shuffle=True,
    )
    val_loader = (
        DataLoader(SequenceDataset(X_val, y_val_scaled), batch_size=max(1, len(X_val)), shuffle=False)
        if has_val
        else None
    )

    model = build_model(config).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay)
    criterion = nn.MSELoss()

    history = TrainingHistory()
    best_state_dict = {k: v.clone() for k, v in model.state_dict().items()}
    epochs_without_improvement = 0

    for epoch in range(config.max_epochs):
        train_loss = _run_epoch(
            model, train_loader, criterion, device, optimizer=optimizer, grad_clip_norm=config.grad_clip_norm
        )
        history.train_loss.append(train_loss)

        # Sem conjunto de validação (série muito curta): usa a perda de
        # treino como critério de early stopping — pior que ter validação
        # real, mas evita travar o treinamento por falta de dados.
        monitored_loss = train_loss
        if val_loader is not None:
            val_loss = _run_epoch(model, val_loader, criterion, device)
            history.val_loss.append(val_loss)
            monitored_loss = val_loss

        if monitored_loss < history.best_val_loss:
            history.best_val_loss = monitored_loss
            history.best_epoch = epoch
            best_state_dict = {k: v.clone() for k, v in model.state_dict().items()}
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1

        if epoch % 10 == 0 or epoch == config.max_epochs - 1:
            logger.info(
                "Epoch %d/%d - train_loss=%.5f%s",
                epoch + 1,
                config.max_epochs,
                train_loss,
                f" val_loss={history.val_loss[-1]:.5f}" if val_loader is not None else "",
            )

        if epochs_without_improvement >= config.early_stopping_patience:
            logger.info("Early stopping na época %d (sem melhora há %d épocas).", epoch + 1, epochs_without_improvement)
            history.stopped_early = True
            break

    model.load_state_dict(best_state_dict)
    return model, scaler, history


def save_checkpoint(
    model: nn.Module,
    scaler: FeatureScaler,
    config: ForecastModelConfig,
    path: Path = DEFAULT_CHECKPOINT_PATH,
) -> Path:
    """Salva pesos do modelo + parâmetros do scaler + config em um único arquivo."""
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "scaler": scaler.to_dict(),
            "config": config.__dict__,
        },
        path,
    )
    logger.info("Checkpoint salvo em %s", path)
    return path
