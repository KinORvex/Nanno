"""
Script standalone de treinamento do modelo de previsão de tendência.

Uso:
    python -m scripts.train_forecaster --project-id <uuid> [--architecture lstm|mlp]

Roda fora do ciclo de request da API — pensado para ser disparado manualmente
ou por um job agendado (cron / Airflow / GitHub Actions) sempre que houver
histórico novo suficiente para justificar um retrain.
"""
import argparse
import logging
import sys
import uuid

from app.core.database import db_session_scope
from app.ml.config import ForecastModelConfig
from app.ml.dataset import InsufficientDataError, build_feature_matrix
from app.ml.train import save_checkpoint, train_model
from app.services.forecast_data import get_daily_time_series

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Treina o modelo de previsão de tendência populacional.")
    parser.add_argument("--project-id", type=str, required=True, help="UUID do AnalysisProject de origem dos dados.")
    parser.add_argument("--architecture", choices=["lstm", "mlp"], default="lstm")
    parser.add_argument("--input-window", type=int, default=14)
    parser.add_argument("--forecast-horizon", type=int, default=7)
    parser.add_argument("--max-epochs", type=int, default=200)
    args = parser.parse_args()

    project_id = uuid.UUID(args.project_id)
    config = ForecastModelConfig(
        architecture=args.architecture,
        input_window=args.input_window,
        forecast_horizon=args.forecast_horizon,
        max_epochs=args.max_epochs,
    )

    with db_session_scope() as db:
        records = get_daily_time_series(db, project_id)

    logger.info("Histórico carregado: %d pontos diários.", len(records))

    try:
        feature_matrix = build_feature_matrix(records)
    except InsufficientDataError as exc:
        logger.error("Não foi possível treinar: %s", exc)
        sys.exit(1)

    model, scaler, history = train_model(feature_matrix, config)
    logger.info(
        "Treino concluído. Melhor época: %d, melhor perda: %.5f, parou cedo: %s",
        history.best_epoch,
        history.best_val_loss,
        history.stopped_early,
    )

    checkpoint_path = save_checkpoint(model, scaler, config)
    logger.info("Modelo salvo em %s", checkpoint_path)


if __name__ == "__main__":
    main()
