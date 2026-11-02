"""Forward-looking unit tests for the Unending Admin API."""

import hashlib
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from api.database.models import RunType
from api.main import api
from api.utils.jobs import ExternalJobClient, get_job_client
from api.utils.prompt import compute_model_prompt_hash


class MockExternalJobClient(ExternalJobClient):
    """Mock external job client returning a fixed external run id."""

    async def create_job(self, job_type: RunType, payload: dict) -> str:
        """Return a fixed external run id without calling the job system."""
        return "mock-external-run-id"


class FailingExternalJobClient(ExternalJobClient):
    """Mock external job client that always fails."""

    async def create_job(self, job_type: RunType, payload: dict) -> str:
        """Raise an httpx error to simulate an external job system failure."""
        raise httpx.ConnectError("mock external job system failure")


def _create_set_with_draft(
    client: TestClient, prompt: str = "a cat"
) -> tuple[str, str, str]:
    """Create a draft set and return (set_id, draft_id, run_id)."""
    created = client.post(
        "/api/v0/sets", json={"model": "black-forest-labs/FLUX.2-klein-4B"}
    )
    set_id = created.json()["set_id"]
    api.dependency_overrides[get_job_client] = lambda: MockExternalJobClient(
        base_url="http://localhost:8080"
    )
    try:
        response = client.post(f"/api/v0/sets/{set_id}/drafts", json={"prompt": prompt})
    finally:
        api.dependency_overrides.pop(get_job_client, None)
    assert response.status_code == 201
    draft_id = response.json()["draft_id"]
    run_id = next(
        run["run_id"]
        for run in client.get("/api/v0/runs", params={"draft_id": draft_id}).json()[
            "runs"
        ]
    )
    return set_id, draft_id, run_id


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


def test_health_alive_returns_200() -> None:
    with TestClient(api) as client:
        response = client.get("/health/alive")
        assert response.status_code == 200
        assert response.json() == {"status": "alive"}


def test_health_ready_returns_200() -> None:
    with TestClient(api) as client:
        response = client.get("/health/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "ready"}


def test_get_run_with_invalid_uuid_returns_422() -> None:
    with TestClient(api) as client:
        response = client.get("/api/v0/runs/not-a-uuid")
        assert response.status_code == 422
        assert response.json()["detail"][0]["type"] == "uuid_parsing"


def test_update_run_status_pending_to_in_progress_returns_200() -> None:
    with TestClient(api) as client:
        _set_id, _draft_id, run_id = _create_set_with_draft(client)
        response = client.put(
            f"/api/v0/runs/{run_id}/status", json={"status": "IN_PROGRESS"}
        )
        assert response.status_code == 200
        status_response = client.get(f"/api/v0/runs/{run_id}")
        assert status_response.status_code == 200
        assert status_response.json()["status"] == "IN_PROGRESS"


def test_update_run_status_in_progress_to_completed_returns_200() -> None:
    with TestClient(api) as client:
        _set_id, _draft_id, run_id = _create_set_with_draft(client)
        response = client.put(
            f"/api/v0/runs/{run_id}/status", json={"status": "IN_PROGRESS"}
        )
        assert response.status_code == 200
        response = client.put(
            f"/api/v0/runs/{run_id}/status", json={"status": "COMPLETED"}
        )
        assert response.status_code == 200
        status_response = client.get(f"/api/v0/runs/{run_id}")
        assert status_response.status_code == 200
        assert status_response.json()["status"] == "COMPLETED"


def test_update_run_status_same_state_returns_200_noop() -> None:
    with TestClient(api) as client:
        _set_id, _draft_id, run_id = _create_set_with_draft(client)
        response = client.put(
            f"/api/v0/runs/{run_id}/status", json={"status": "IN_PROGRESS"}
        )
        assert response.status_code == 200
        response = client.put(
            f"/api/v0/runs/{run_id}/status", json={"status": "IN_PROGRESS"}
        )
        assert response.status_code == 200
        status_response = client.get(f"/api/v0/runs/{run_id}")
        assert status_response.status_code == 200
        assert status_response.json()["status"] == "IN_PROGRESS"


def test_update_run_status_failed_propagates_to_draft_returns_200() -> None:
    with TestClient(api) as client:
        set_id, draft_id, run_id = _create_set_with_draft(client)
        response = client.put(
            f"/api/v0/runs/{run_id}/status", json={"status": "FAILED"}
        )
        assert response.status_code == 200
        draft_response = client.get(f"/api/v0/sets/{set_id}/drafts/{draft_id}")
        assert draft_response.status_code == 200
        assert draft_response.json()["status"] == "FAILED"


def test_redo_run_returns_new_run_returns_201() -> None:
    with TestClient(api) as client:
        _set_id, _draft_id, run_id = _create_set_with_draft(client)
        response = client.put(
            f"/api/v0/runs/{run_id}/status", json={"status": "FAILED"}
        )
        assert response.status_code == 200
        api.dependency_overrides[get_job_client] = lambda: MockExternalJobClient(
            base_url="http://localhost:8080"
        )
        try:
            response = client.post(f"/api/v0/runs/{run_id}")
        finally:
            api.dependency_overrides.pop(get_job_client, None)
        assert response.status_code == 201
        new_run_id = response.json()["run_id"]
        new_run_response = client.get(f"/api/v0/runs/{new_run_id}")
        assert new_run_response.status_code == 200
        assert new_run_response.json()["status"] == "PENDING"


def test_commit_draft_returns_200_and_commits_set() -> None:
    with TestClient(api) as client:
        set_id, draft_id, run_id = _create_set_with_draft(client)
        client.patch(
            f"/api/v0/sets/{set_id}",
            json={"slug": "commit-set-abc", "name": "Commit Set"},
        )
        response = client.put(
            f"/api/v0/runs/{run_id}/status", json={"status": "IN_PROGRESS"}
        )
        assert response.status_code == 200
        response = client.put(
            f"/api/v0/runs/{run_id}/status", json={"status": "COMPLETED"}
        )
        assert response.status_code == 200
        api.dependency_overrides[get_job_client] = lambda: MockExternalJobClient(
            base_url="http://localhost:8080"
        )
        try:
            response = client.post(f"/api/v0/sets/{set_id}/drafts/{draft_id}/commit")
        finally:
            api.dependency_overrides.pop(get_job_client, None)
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "COMMITTED"
        set_response = client.get(f"/api/v0/sets/{set_id}")
        assert set_response.status_code == 200
        assert set_response.json()["status"] == "COMMITTED"


def test_update_run_status_invalid_transition_returns_400() -> None:
    with TestClient(api) as client:
        _set_id, _draft_id, run_id = _create_set_with_draft(client)
        response = client.put(
            f"/api/v0/runs/{run_id}/status", json={"status": "COMPLETED"}
        )
        assert response.status_code == 400
        assert "Invalid run status transition" in response.json()["detail"]


def test_update_run_status_not_found_returns_404() -> None:
    with TestClient(api) as client:
        response = client.put(
            f"/api/v0/runs/{uuid4()}/status", json={"status": "IN_PROGRESS"}
        )
        assert response.status_code == 404


def test_redo_run_requires_failed_status_returns_400() -> None:
    with TestClient(api) as client:
        _set_id, _draft_id, run_id = _create_set_with_draft(client)
        response = client.post(f"/api/v0/runs/{run_id}")
        assert response.status_code == 400
        assert "FAILED" in response.json()["detail"]


def test_commit_draft_with_draft_not_completed_returns_400() -> None:
    with TestClient(api) as client:
        set_id, draft_id, _run_id = _create_set_with_draft(client)
        client.patch(
            f"/api/v0/sets/{set_id}",
            json={"slug": "commit-set-abc", "name": "Commit Set"},
        )
        response = client.post(f"/api/v0/sets/{set_id}/drafts/{draft_id}/commit")
        assert response.status_code == 400
        assert "COMPLETED" in response.json()["detail"]


def test_commit_draft_with_missing_slug_and_name_returns_400() -> None:
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
        response = client.post(f"/api/v0/sets/{set_id}/drafts/{draft_id}/commit")
        assert response.status_code == 400
        assert "slug and name" in response.json()["detail"]


def test_create_draft_on_missing_set_returns_404() -> None:
    with TestClient(api) as client:
        response = client.post(
            f"/api/v0/sets/{uuid4()}/drafts", json={"prompt": "a cat"}
        )
        assert response.status_code == 404


def test_create_draft_on_non_draft_set_returns_400() -> None:
    with TestClient(api) as client:
        created = client.post(
            "/api/v0/sets", json={"model": "black-forest-labs/FLUX.2-klein-4B"}
        )
        set_id = created.json()["set_id"]
        response = client.delete(f"/api/v0/sets/{set_id}")
        assert response.status_code == 200
        response = client.post(
            f"/api/v0/sets/{set_id}/drafts", json={"prompt": "a cat"}
        )
        assert response.status_code == 400


def test_patch_set_not_found_returns_404() -> None:
    with TestClient(api) as client:
        response = client.patch(f"/api/v0/sets/{uuid4()}", json={"slug": "some-set"})
        assert response.status_code == 404


def test_patch_set_not_draft_returns_400() -> None:
    with TestClient(api) as client:
        created = client.post(
            "/api/v0/sets", json={"model": "black-forest-labs/FLUX.2-klein-4B"}
        )
        set_id = created.json()["set_id"]
        response = client.delete(f"/api/v0/sets/{set_id}")
        assert response.status_code == 200
        response = client.patch(f"/api/v0/sets/{set_id}", json={"slug": "some-set"})
        assert response.status_code == 400


def test_delete_set_not_found_returns_404() -> None:
    with TestClient(api) as client:
        response = client.delete(f"/api/v0/sets/{uuid4()}")
        assert response.status_code == 404


def test_delete_set_not_draft_returns_400() -> None:
    with TestClient(api) as client:
        created = client.post(
            "/api/v0/sets", json={"model": "black-forest-labs/FLUX.2-klein-4B"}
        )
        set_id = created.json()["set_id"]
        response = client.delete(f"/api/v0/sets/{set_id}")
        assert response.status_code == 200
        response = client.delete(f"/api/v0/sets/{set_id}")
        assert response.status_code == 400


def test_create_set_with_invalid_slug_returns_422() -> None:
    with TestClient(api) as client:
        response = client.post(
            "/api/v0/sets",
            json={"model": "black-forest-labs/FLUX.2-klein-4B", "slug": "Bad Slug"},
        )
        assert response.status_code == 422


def test_create_set_with_long_name_returns_422() -> None:
    with TestClient(api) as client:
        response = client.post(
            "/api/v0/sets",
            json={"model": "black-forest-labs/FLUX.2-klein-4B", "name": "x" * 65},
        )
        assert response.status_code == 422


def test_create_set_with_empty_name_returns_422() -> None:
    with TestClient(api) as client:
        response = client.post(
            "/api/v0/sets",
            json={"model": "black-forest-labs/FLUX.2-klein-4B", "name": ""},
        )
        assert response.status_code == 422


def test_list_sets_by_status_returns_abandoned_set() -> None:
    with TestClient(api) as client:
        created = client.post(
            "/api/v0/sets", json={"model": "black-forest-labs/FLUX.2-klein-4B"}
        )
        set_id = created.json()["set_id"]
        response = client.delete(f"/api/v0/sets/{set_id}")
        assert response.status_code == 200
        response = client.get("/api/v0/sets", params={"status": "ABANDONED"})
        assert response.status_code == 200
        body = response.json()
        assert any(s["set_id"] == set_id for s in body["sets"])


def test_compute_model_prompt_hash_returns_sha256_of_model_and_prompt() -> None:
    model = "black-forest-labs/FLUX.2-klein-4B"
    prompt = "a cat"
    assert (
        compute_model_prompt_hash(model, prompt)
        == hashlib.sha256(f"{model}::{prompt}".encode()).hexdigest()
    )


def test_create_draft_with_failing_job_returns_500() -> None:
    with TestClient(api) as client:
        created = client.post(
            "/api/v0/sets", json={"model": "black-forest-labs/FLUX.2-klein-4B"}
        )
        set_id = created.json()["set_id"]
        api.dependency_overrides[get_job_client] = lambda: FailingExternalJobClient(
            base_url="http://localhost:8080"
        )
        try:
            response = client.post(
                f"/api/v0/sets/{set_id}/drafts", json={"prompt": "a cat"}
            )
        finally:
            api.dependency_overrides.pop(get_job_client, None)
        assert response.status_code == 500
        assert response.json()["detail"] == "Failed to create external job."
