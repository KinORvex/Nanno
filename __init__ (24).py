"""
Modulo de Inteligencia Artificial para previsao de tendencia populacional de
Nannochloropsis, usando PyTorch (LSTM, com MLP como baseline alternativo).

Nao possui nenhuma dependencia de FastAPI/SQLAlchemy: recebe e devolve
arrays NumPy / tensores, o que permite treinar e testar o modelo de forma
isolada (script, notebook, job de treino) sem subir a API ou o banco.

Uso tipico (treino):

    from app.ml.config import DEFAULT_CONFIG
    from app.ml.dataset import build_feature_matrix
    from app.ml.train import train_model, save_checkpoint

    feature_matrix = build_feature_matrix(records)
    model, scaler, history = train_model(feature_matrix, DEFAULT_CONFIG)
    save_checkpoint(model, scaler, DEFAULT_CONFIG)

Uso tipico (inferencia, ja coberto pelo endpoint /forecast):

    from app.ml.inference import ForecastModelRegistry

    registry = ForecastModelRegistry.get_instance()
    forecast = registry.predict(feature_matrix)
"""
