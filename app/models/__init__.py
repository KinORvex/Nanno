"""
Importa todos os models em um unico ponto para que:
1. `Base.metadata` conheca todas as tabelas (necessario para Alembic autogenerate
   e para `Base.metadata.create_all` em ambientes de teste).
2. As referencias de relationship por string (ex.: "User", "AnalysisProject")
   sejam resolvidas corretamente pelo SQLAlchemy.

Modulos adicionados nesta etapa (Experiment/Culture/Observation/ImageAnalysis/
DigitalTwinState/Prediction) seguem exatamente o mesmo padrao dos modulos
ja existentes acima -- nenhum model existente foi removido ou renomeado.
"""
from app.core.database import Base  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.project import AnalysisProject, ProjectStatus  # noqa: F401
from app.models.image import MicroalgaeImage, ProcessingStatus  # noqa: F401
from app.models.trend import TrendEstimate, TrendDirection, TrendMetric  # noqa: F401
from app.models.environment import EnvironmentalReading  # noqa: F401
from app.models.experiment import Experiment, ExperimentStatus  # noqa: F401
from app.models.culture import Culture  # noqa: F401
from app.models.observation import Observation  # noqa: F401
from app.models.image_analysis import ImageAnalysis  # noqa: F401
from app.models.digital_twin import DigitalTwinState, HealthStatus  # noqa: F401
from app.models.prediction import Prediction  # noqa: F401

__all__ = [
    "Base",
    "User",
    "AnalysisProject",
    "ProjectStatus",
    "MicroalgaeImage",
    "ProcessingStatus",
    "TrendEstimate",
    "TrendDirection",
    "TrendMetric",
    "EnvironmentalReading",
    "Experiment",
    "ExperimentStatus",
    "Culture",
    "Observation",
    "ImageAnalysis",
    "DigitalTwinState",
    "HealthStatus",
    "Prediction",
]
