"""
Testes do Digital Twin: armazenamento de métricas, criação/atualização de
estado, avaliação de estado, e comportamento com dados insuficientes.

Insere ImageAnalysis diretamente no banco (em vez de subir imagens reais)
para isolar o comportamento do Digital Twin da pipeline de CV, testada
separadamente.
"""
from datetime import datetime, timedelta, timezone

from app.crud.culture import create_culture
from app.crud.experiment import create_experiment
from app.crud.observation import create_observation
from app.models.digital_twin import HealthStatus
from app.models.image import MicroalgaeImage, ProcessingStatus
from app.models.image_analysis import ImageAnalysis
from app.schemas.culture import CultureCreate
from app.schemas.experiment import ExperimentCreate
from app.schemas.observation import ObservationCreate
from app.services.digital_twin.digital_twin_service import compute_digital_twin_state


def _create_culture(db_session, test_project, label="C1", condition="controle"):
    experiment = create_experiment(db_session, project_id=test_project.id, experiment_in=ExperimentCreate(name="Exp"))
    culture = create_culture(
        db_session,
        experiment_id=experiment.id,
        culture_in=CultureCreate(label=label, condition_label=condition, started_at=datetime.now(timezone.utc)),
    )
    return experiment, culture


def _add_observation_with_metrics(db_session, culture, day_offset, diameter_mean, cell_count):
    observed_at = datetime.now(timezone.utc) + timedelta(days=day_offset)
    observation = create_observation(db_session, culture=culture, observation_in=ObservationCreate(observed_at=observed_at))

    image = MicroalgaeImage(
        project_id=culture.experiment.project_id,
        observation_id=observation.id,
        original_filename="test.png",
        s3_bucket="test-bucket",
        s3_key=f"test/{observation.id}.png",
        content_type="image/png",
        file_size_bytes=100,
        processing_status=ProcessingStatus.COMPLETED,
        cell_count=cell_count,
        avg_cell_diameter_um=diameter_mean,
    )
    db_session.add(image)
    db_session.commit()
    db_session.refresh(image)

    analysis = ImageAnalysis(
        image_id=image.id,
        observation_id=observation.id,
        status=ProcessingStatus.COMPLETED,
        algorithm_name="nannochloropsis_watershed",
        algorithm_version="v1",
        metrics={
            "cell_count": cell_count,
            "diameter_mean_um": diameter_mean,
            "diameter_cv": 0.15,
            "cell_density_cells_per_ml": cell_count * 1000,
        },
    )
    db_session.add(analysis)
    db_session.commit()
    return observation, analysis


def test_digital_twin_unknown_with_insufficient_data(db_session, test_project):
    _, culture = _create_culture(db_session, test_project)
    _add_observation_with_metrics(db_session, culture, day_offset=0, diameter_mean=3.0, cell_count=1000)

    state = compute_digital_twin_state(db_session, culture, persist=True)
    assert state.health_status == HealthStatus.UNKNOWN
    assert state.stress_score is None
    assert state.confidence is None


def test_digital_twin_detects_stress(db_session, test_project):
    _, culture = _create_culture(db_session, test_project, label="N1", condition="privacao_nitrogenio")

    baseline_diameters = [3.00, 3.04, 2.97, 3.02]
    for day, d in enumerate(baseline_diameters):
        _add_observation_with_metrics(db_session, culture, day_offset=day, diameter_mean=d, cell_count=1000 + day * 100)

    culture.stress_induced_at = datetime.now(timezone.utc) + timedelta(days=4)
    db_session.commit()

    for day in range(4, 8):
        _add_observation_with_metrics(db_session, culture, day_offset=day, diameter_mean=3.9, cell_count=1000 + day * 20)

    state = compute_digital_twin_state(db_session, culture, persist=True)
    assert state.health_status == HealthStatus.STRESSED
    assert state.stress_score is not None and state.stress_score > 2.0
    assert "diameter_mean_um" in (state.contributing_factors or {})


def test_digital_twin_state_persisted_as_history(db_session, test_project):
    _, culture = _create_culture(db_session, test_project)
    for day in range(4):
        _add_observation_with_metrics(db_session, culture, day_offset=day, diameter_mean=3.0, cell_count=1000)

    state1 = compute_digital_twin_state(db_session, culture, persist=True)
    state2 = compute_digital_twin_state(db_session, culture, persist=True)

    assert state1.id != state2.id  # cada calculo gera um snapshot novo (append-only, nao sobrescreve)
    db_session.refresh(culture)
    assert len(culture.digital_twin_states) == 2


def test_growth_state_reflects_increasing_trend(db_session, test_project):
    _, culture = _create_culture(db_session, test_project)
    for day, count in enumerate([1000, 1200, 1500, 1900]):
        _add_observation_with_metrics(db_session, culture, day_offset=day, diameter_mean=3.0, cell_count=count)

    state = compute_digital_twin_state(db_session, culture, persist=True)
    assert state.growth_state == "increasing"


def test_healthy_growth_does_not_trigger_stress_false_positive(db_session, test_project):
    """Regressão do bug encontrado durante o desenvolvimento: contagem de
    células crescendo normalmente não deve, isoladamente, disparar estresse."""
    _, culture = _create_culture(db_session, test_project)
    diameters = [3.00, 3.04, 2.97, 3.02, 3.01, 2.99]
    for day, d in enumerate(diameters):
        _add_observation_with_metrics(db_session, culture, day_offset=day, diameter_mean=d, cell_count=1000 + day * 50)

    state = compute_digital_twin_state(db_session, culture, persist=True)
    assert state.health_status == HealthStatus.NORMAL
