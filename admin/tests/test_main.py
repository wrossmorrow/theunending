"""Forward-looking unit tests for the Unending Admin API."""

from uuid import uuid4

from fastapi.testclient import TestClient

from api.database.models import RunType
from api.main import api
from api.utils.jobs import ExternalJobClient, get_job_client


class MockExternalJobClient(ExternalJobClient):
    """Mock external job client returning a fixed external run id."""

    async def create_job(self, job_type: RunType, payload: dict) -> str:
        """Return a fixed external run id without calling the job system."""
        return "mock-external-run-id"


def test_get_set_with_invalid_uuid_returns_422() -> None:
    with TestClient(api) as client:
        response = client.get("/api/v0/sets/not-a-uuid")
        assert response.status_code == 422
        assert response.json()["detail"][0]["type"] == "uuid_parsing"


def test_create_set_without_model_returns_422() -> None:
    with TestClient(api) as client:
        response = client.post("/api/v0/sets", json={})
        assert response.status_code == 422


def test_create_set_returns_201_with_draft_status() -> None:
    with TestClient(api) as client:
        response = client.post(
            "/api/v0/sets", json={"model": "black-forest-labs/FLUX.2-klein-4B"}
        )
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "DRAFT"


def test_patch_set_updates_slug_and_name() -> None:
    with TestClient(api) as client:
        created = client.post(
            "/api/v0/sets", json={"model": "black-forest-labs/FLUX.2-klein-4B"}
        )
        set_id = created.json()["set_id"]

        response = client.patch(
            f"/api/v0/sets/{set_id}", json={"slug": "my-set", "name": "My Set"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["slug"] == "my-set"
        assert body["name"] == "My Set"
        assert body["status"] == "DRAFT"


def test_delete_set_marks_abandoned() -> None:
    with TestClient(api) as client:
        created = client.post(
            "/api/v0/sets", json={"model": "black-forest-labs/FLUX.2-klein-4B"}
        )
        set_id = created.json()["set_id"]

        response = client.delete(f"/api/v0/sets/{set_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "ABANDONED"


def test_create_draft_returns_201_with_pending_run() -> None:
    with TestClient(api) as client:
        created = client.post(
            "/api/v0/sets", json={"model": "black-forest-labs/FLUX.2-klein-4B"}
        )
        set_id = created.json()["set_id"]
        api.dependency_overrides[get_job_client] = lambda: MockExternalJobClient(
            base_url="http://localhost:8080"
        )
        try:
            response = client.post(
                f"/api/v0/sets/{set_id}/drafts", json={"prompt": "a cat"}
            )
        finally:
            api.dependency_overrides.pop(get_job_client, None)
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "PENDING"


def test_create_draft_with_long_prompt_returns_422() -> None:
    with TestClient(api) as client:
        created = client.post(
            "/api/v0/sets", json={"model": "black-forest-labs/FLUX.2-klein-4B"}
        )
        set_id = created.json()["set_id"]
        api.dependency_overrides[get_job_client] = lambda: MockExternalJobClient(
            base_url="http://localhost:8080"
        )
        try:
            response = client.post(
                f"/api/v0/sets/{set_id}/drafts", json={"prompt": "a" * 1024}
            )
        finally:
            api.dependency_overrides.pop(get_job_client, None)
        assert response.status_code == 422


def test_create_draft_with_empty_prompt_returns_422() -> None:
    with TestClient(api) as client:
        created = client.post(
            "/api/v0/sets", json={"model": "black-forest-labs/FLUX.2-klein-4B"}
        )
        set_id = created.json()["set_id"]
        api.dependency_overrides[get_job_client] = lambda: MockExternalJobClient(
            base_url="http://localhost:8080"
        )
        try:
            response = client.post(f"/api/v0/sets/{set_id}/drafts", json={"prompt": ""})
        finally:
            api.dependency_overrides.pop(get_job_client, None)
        assert response.status_code == 422


def test_list_sets_returns_created_set() -> None:
    with TestClient(api) as client:
        created = client.post(
            "/api/v0/sets", json={"model": "black-forest-labs/FLUX.2-klein-4B"}
        )
        set_id = created.json()["set_id"]
        response = client.get("/api/v0/sets")
        assert response.status_code == 200
        body = response.json()
        assert any(s["set_id"] == set_id for s in body["sets"])


def test_get_set_returns_created_set() -> None:
    with TestClient(api) as client:
        created = client.post(
            "/api/v0/sets", json={"model": "black-forest-labs/FLUX.2-klein-4B"}
        )
        set_id = created.json()["set_id"]
        response = client.get(f"/api/v0/sets/{set_id}")
        assert response.status_code == 200
        assert response.json()["set_id"] == set_id
        response = client.get(f"/api/v0/sets/{uuid4()}")
        assert response.status_code == 404


def test_list_drafts_returns_created_draft() -> None:
    with TestClient(api) as client:
        created = client.post(
            "/api/v0/sets", json={"model": "black-forest-labs/FLUX.2-klein-4B"}
        )
        set_id = created.json()["set_id"]
        api.dependency_overrides[get_job_client] = lambda: MockExternalJobClient(
            base_url="http://localhost:8080"
        )
        try:
            response = client.post(
                f"/api/v0/sets/{set_id}/drafts", json={"prompt": "a cat"}
            )
        finally:
            api.dependency_overrides.pop(get_job_client, None)
        assert response.status_code == 201
        draft_id = response.json()["draft_id"]
        response = client.get(f"/api/v0/sets/{set_id}/drafts")
        assert response.status_code == 200
        body = response.json()
        assert any(d["draft_id"] == draft_id for d in body["drafts"])


def test_get_draft_returns_created_draft() -> None:
    with TestClient(api) as client:
        created = client.post(
            "/api/v0/sets", json={"model": "black-forest-labs/FLUX.2-klein-4B"}
        )
        set_id = created.json()["set_id"]
        api.dependency_overrides[get_job_client] = lambda: MockExternalJobClient(
            base_url="http://localhost:8080"
        )
        try:
            response = client.post(
                f"/api/v0/sets/{set_id}/drafts", json={"prompt": "a cat"}
            )
        finally:
            api.dependency_overrides.pop(get_job_client, None)
        assert response.status_code == 201
        draft_id = response.json()["draft_id"]
        response = client.get(f"/api/v0/sets/{set_id}/drafts/{draft_id}")
        assert response.status_code == 200
        assert response.json()["draft_id"] == draft_id
        response = client.get(f"/api/v0/sets/{set_id}/drafts/{uuid4()}")
        assert response.status_code == 404


def test_list_runs_returns_created_run() -> None:
    with TestClient(api) as client:
        created = client.post(
            "/api/v0/sets", json={"model": "black-forest-labs/FLUX.2-klein-4B"}
        )
        set_id = created.json()["set_id"]
        api.dependency_overrides[get_job_client] = lambda: MockExternalJobClient(
            base_url="http://localhost:8080"
        )
        try:
            response = client.post(
                f"/api/v0/sets/{set_id}/drafts", json={"prompt": "a cat"}
            )
        finally:
            api.dependency_overrides.pop(get_job_client, None)
        assert response.status_code == 201
        draft_id = response.json()["draft_id"]
        response = client.get("/api/v0/runs", params={"draft_id": draft_id})
        assert response.status_code == 200
        body = response.json()
        assert any(r["draft_id"] == str(draft_id) for r in body["runs"])


def test_get_run_returns_created_run() -> None:
    with TestClient(api) as client:
        created = client.post(
            "/api/v0/sets", json={"model": "black-forest-labs/FLUX.2-klein-4B"}
        )
        set_id = created.json()["set_id"]
        api.dependency_overrides[get_job_client] = lambda: MockExternalJobClient(
            base_url="http://localhost:8080"
        )
        try:
            response = client.post(
                f"/api/v0/sets/{set_id}/drafts", json={"prompt": "a cat"}
            )
        finally:
            api.dependency_overrides.pop(get_job_client, None)
        assert response.status_code == 201
        draft_id = response.json()["draft_id"]
        response = client.get("/api/v0/runs", params={"draft_id": draft_id})
        assert response.status_code == 200
        run_id = response.json()["runs"][0]["run_id"]
        response = client.get(f"/api/v0/runs/{run_id}")
        assert response.status_code == 200
        assert response.json()["run_id"] == run_id
        response = client.get(f"/api/v0/runs/{uuid4()}")
        assert response.status_code == 404
