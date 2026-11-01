"""Forward-looking unit tests for the Unending Admin API."""

from uuid import uuid4

from fastapi.testclient import TestClient

from api.main import api


def test_get_set_with_invalid_uuid_returns_422() -> None:
    with TestClient(api) as client:
        response = client.get("/api/v0/sets/not-a-uuid")
        assert response.status_code == 422
        assert response.json()["detail"][0]["type"] == "uuid_parsing"


def test_create_set_without_model_returns_422() -> None:
    with TestClient(api) as client:
        response = client.post("/api/v0/sets", json={})
        assert response.status_code == 422


def test_list_sets_not_implemented_returns_501() -> None:
    with TestClient(api) as client:
        response = client.get("/api/v0/sets")
        assert response.status_code == 501
        assert "detail" in response.json()


def test_create_set_not_implemented_returns_501() -> None:
    with TestClient(api) as client:
        response = client.post(
            "/api/v0/sets", json={"model": "black-forest-labs/FLUX.2-klein-4B"}
        )
        assert response.status_code == 501
        assert "detail" in response.json()


def test_get_set_not_implemented_returns_501() -> None:
    with TestClient(api) as client:
        response = client.get(f"/api/v0/sets/{uuid4()}")
        assert response.status_code == 501
        assert "detail" in response.json()


def test_delete_set_not_implemented_returns_501() -> None:
    with TestClient(api) as client:
        response = client.delete(f"/api/v0/sets/{uuid4()}")
        assert response.status_code == 501
        assert "detail" in response.json()
