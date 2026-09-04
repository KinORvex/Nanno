"""Testes de criação/listagem/autorização de Experiment."""
import uuid


def test_create_experiment(client, auth_headers, test_project):
    response = client.post(
        f"/api/v1/projects/{test_project.id}/experiments",
        json={"name": "Privação de nitrogênio", "hypothesis": "T_m < T_g"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Privação de nitrogênio"
    assert data["project_id"] == str(test_project.id)
    assert data["status"] == "planning"


def test_list_experiments(client, auth_headers, test_project):
    client.post(f"/api/v1/projects/{test_project.id}/experiments", json={"name": "Exp 1"}, headers=auth_headers)
    client.post(f"/api/v1/projects/{test_project.id}/experiments", json={"name": "Exp 2"}, headers=auth_headers)

    response = client.get(f"/api/v1/projects/{test_project.id}/experiments", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_cannot_create_experiment_in_other_users_project(client, other_auth_headers, test_project):
    """Autorização: um usuário não pode criar experimento em projeto de outro usuário."""
    response = client.post(
        f"/api/v1/projects/{test_project.id}/experiments",
        json={"name": "Tentativa indevida"},
        headers=other_auth_headers,
    )
    assert response.status_code == 404  # não revela existência do projeto a quem não é dono


def test_create_experiment_without_auth_fails(client, test_project):
    response = client.post(
        f"/api/v1/projects/{test_project.id}/experiments",
        json={"name": "Sem token"},
    )
    assert response.status_code == 401


def test_get_nonexistent_experiment_returns_404(client, auth_headers):
    response = client.get(f"/api/v1/experiments/{uuid.uuid4()}", headers=auth_headers)
    assert response.status_code == 404


def test_update_experiment_status(client, auth_headers, test_project):
    exp = client.post(
        f"/api/v1/projects/{test_project.id}/experiments", json={"name": "Exp"}, headers=auth_headers
    ).json()

    response = client.patch(
        f"/api/v1/experiments/{exp['id']}", json={"status": "active"}, headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["status"] == "active"
