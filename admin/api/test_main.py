"""Forward-looking unit tests for the Unending Admin API."""

from fastapi.testclient import TestClient

from api.main import api

client = TestClient(api)


def test_get_set_with_invalid_uuid_returns_422() -> None:
    response = client.get("/api/v0/sets/not-a-uuid")
    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "uuid_parsing"


def test_list_sets_success_response_shape() -> None:
    response = client.get("/api/v0/sets")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, dict)
    assert isinstance(body["sets"], list)
