"""Testes de criação de Culture e da cadeia Project -> Experiment -> Culture."""


def _create_experiment(client, auth_headers, project_id, name="Exp"):
    r = client.post(f"/api/v1/projects/{project_id}/experiments", json={"name": name}, headers=auth_headers)
    assert r.status_code == 201
    return r.json()


def test_create_culture(client, auth_headers, test_project):
    experiment = _create_experiment(client, auth_headers, test_project.id)
    response = client.post(
        f"/api/v1/experiments/{experiment['id']}/cultures",
        json={"label": "C1", "condition_label": "controle"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["label"] == "C1"
    assert data["experiment_id"] == experiment["id"]


def test_project_experiment_culture_chain(client, auth_headers, test_project):
    """Confirma a cadeia completa Project -> Experiment -> Culture."""
    experiment = _create_experiment(client, auth_headers, test_project.id, name="Cadeia")
    culture = client.post(
        f"/api/v1/experiments/{experiment['id']}/cultures",
        json={"label": "N1", "condition_label": "privacao_nitrogenio"},
        headers=auth_headers,
    ).json()

    detail = client.get(f"/api/v1/cultures/{culture['id']}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["experiment_id"] == experiment["id"]
    assert experiment["project_id"] == str(test_project.id)


def test_cannot_access_culture_of_other_user(client, auth_headers, other_auth_headers, test_project):
    experiment = _create_experiment(client, auth_headers, test_project.id)
    culture = client.post(
        f"/api/v1/experiments/{experiment['id']}/cultures",
        json={"label": "C1", "condition_label": "controle"},
        headers=auth_headers,
    ).json()

    response = client.get(f"/api/v1/cultures/{culture['id']}", headers=other_auth_headers)
    assert response.status_code == 404


def test_compare_requires_at_least_two_ids(client, auth_headers, test_project):
    experiment = _create_experiment(client, auth_headers, test_project.id)
    culture = client.post(
        f"/api/v1/experiments/{experiment['id']}/cultures",
        json={"label": "C1", "condition_label": "controle"},
        headers=auth_headers,
    ).json()

    response = client.get("/api/v1/cultures/compare", params={"ids": [culture["id"]]}, headers=auth_headers)
    assert response.status_code == 422


def test_compare_route_not_shadowed_by_culture_id_route(client, auth_headers, test_project):
    """Regressão: /cultures/compare precisa ser resolvida como a rota de
    comparação, não como /cultures/{culture_id} com culture_id='compare'."""
    experiment = _create_experiment(client, auth_headers, test_project.id)
    c1 = client.post(
        f"/api/v1/experiments/{experiment['id']}/cultures",
        json={"label": "C1", "condition_label": "controle"},
        headers=auth_headers,
    ).json()
    c2 = client.post(
        f"/api/v1/experiments/{experiment['id']}/cultures",
        json={"label": "N1", "condition_label": "privacao_nitrogenio"},
        headers=auth_headers,
    ).json()

    response = client.get("/api/v1/cultures/compare", params={"ids": [c1["id"], c2["id"]]}, headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()["cultures"]) == 2
