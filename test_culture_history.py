"""Testes de recuperação de histórico (GET /cultures/{id}/history), cobrindo
armazenamento/recuperação de métricas de ImageAnalysis pela API.

A métrica é inserida diretamente no banco (sem upload de imagem real) para
isolar o teste do pipeline de visão computacional, que já é validado
separadamente pelos testes de `app/services/cell_analysis`.
"""
from datetime import datetime, timezone

from app.models.image import MicroalgaeImage, ProcessingStatus
from app.models.image_analysis import ImageAnalysis


def test_culture_history_endpoint_returns_metrics_and_timeline(client, auth_headers, db_session, test_project):
    exp = client.post(
        f"/api/v1/projects/{test_project.id}/experiments", json={"name": "Exp"}, headers=auth_headers
    ).json()
    culture = client.post(
        f"/api/v1/experiments/{exp['id']}/cultures",
        json={"label": "C1", "condition_label": "controle", "started_at": datetime.now(timezone.utc).isoformat()},
        headers=auth_headers,
    ).json()

    obs_resp = client.post(f"/api/v1/cultures/{culture['id']}/observations", json={}, headers=auth_headers)
    observation_id = obs_resp.json()["id"]

    image = MicroalgaeImage(
        project_id=test_project.id,
        observation_id=observation_id,
        original_filename="x.png",
        s3_bucket="b",
        s3_key="k",
        content_type="image/png",
        file_size_bytes=10,
        processing_status=ProcessingStatus.COMPLETED,
    )
    db_session.add(image)
    db_session.commit()
    db_session.refresh(image)

    analysis = ImageAnalysis(
        image_id=image.id,
        observation_id=observation_id,
        status=ProcessingStatus.COMPLETED,
        algorithm_name="nannochloropsis_watershed",
        algorithm_version="v1",
        metrics={"cell_count": 1500, "diameter_mean_um": 3.2, "diameter_cv": 0.12},
    )
    db_session.add(analysis)
    db_session.commit()

    history = client.get(f"/api/v1/cultures/{culture['id']}/history", headers=auth_headers)
    assert history.status_code == 200
    data = history.json()
    assert data["culture_id"] == culture["id"]
    assert len(data["points"]) == 1
    assert data["points"][0]["metrics"]["cell_count"] == 1500
    assert data["points"][0]["observation_id"] == observation_id


def test_history_of_culture_with_no_observations_is_empty_not_error(client, auth_headers, test_project):
    exp = client.post(
        f"/api/v1/projects/{test_project.id}/experiments", json={"name": "Exp"}, headers=auth_headers
    ).json()
    culture = client.post(
        f"/api/v1/experiments/{exp['id']}/cultures",
        json={"label": "C1", "condition_label": "controle"},
        headers=auth_headers,
    ).json()

    response = client.get(f"/api/v1/cultures/{culture['id']}/history", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["points"] == []
