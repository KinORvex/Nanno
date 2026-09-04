"""Testes de criação de Observation e cálculo de relative_hours."""
from datetime import datetime, timezone


def _setup_culture(client, auth_headers, project_id):
    exp = client.post(f"/api/v1/projects/{project_id}/experiments", json={"name": "Exp"}, headers=auth_headers).json()
    started_at = datetime.now(timezone.utc).isoformat()
    culture = client.post(
        f"/api/v1/experiments/{exp['id']}/cultures",
        json={"label": "C1", "condition_label": "controle", "started_at": started_at},
        headers=auth_headers,
    ).json()
    return culture


def test_create_observation(client, auth_headers, test_project):
    culture = _setup_culture(client, auth_headers, test_project.id)
    response = client.post(f"/api/v1/cultures/{culture['id']}/observations", json={}, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["culture_id"] == culture["id"]
    # culture tem started_at definido -> relative_hours deve ser calculado e >= 0
    assert data["relative_hours"] is not None
    assert data["relative_hours"] >= 0


def test_observation_without_culture_started_at_has_null_relative_hours(client, auth_headers, test_project):
    exp = client.post(
        f"/api/v1/projects/{test_project.id}/experiments", json={"name": "Exp"}, headers=auth_headers
    ).json()
    culture = client.post(
        f"/api/v1/experiments/{exp['id']}/cultures",
        json={"label": "C1", "condition_label": "controle"},  # sem started_at
        headers=auth_headers,
    ).json()

    response = client.post(f"/api/v1/cultures/{culture['id']}/observations", json={}, headers=auth_headers)
    assert response.status_code == 201
    assert response.json()["relative_hours"] is None


def test_list_observations_ordered_by_time(client, auth_headers, test_project):
    culture = _setup_culture(client, auth_headers, test_project.id)
    client.post(f"/api/v1/cultures/{culture['id']}/observations", json={}, headers=auth_headers)
    client.post(f"/api/v1/cultures/{culture['id']}/observations", json={}, headers=auth_headers)

    response = client.get(f"/api/v1/cultures/{culture['id']}/observations", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["observed_at"] <= data[1]["observed_at"]
