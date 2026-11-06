"""Forward-looking unit tests for the Unending Admin API."""

import asyncio
import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.database import models as database
from api.main import api
from api.settings import settings
from api.utils.jobs import (
    ExternalJobClient,
    JobAPIResponse,
    JobRequest,
    get_job_client,
)
from api.utils.prompt import compute_model_prompt_hash
from api.utils.publish import Publisher, PublishRequest, get_publisher


class MockExternalJobClient(ExternalJobClient):
    """Mock external job client that records enqueued job requests."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Create a mock client that records enqueued job requests."""
        super().__init__(
            base_url=settings.job_base_url, session_factory=session_factory
        )
        self.enqueued_requests: list[JobRequest] = []

    async def request_job(self, job_request: JobRequest) -> None:
        """Record an enqueued job request without submitting it."""
        self.enqueued_requests.append(job_request)


class FailingExternalJobClient(MockExternalJobClient):
    """Mock external job client that fails to enqueue job requests."""

    async def request_job(self, job_request: JobRequest) -> None:
        """Raise an httpx error to simulate an external job system failure."""
        raise httpx.ConnectError("mock external job system failure")


@contextmanager
def mock_job_client(
    session_factory: async_sessionmaker[AsyncSession],
) -> Iterator[MockExternalJobClient]:
    """Override the job client dependency with a mock that records enqueues."""
    client = MockExternalJobClient(session_factory=session_factory)
    api.dependency_overrides[get_job_client] = lambda: client
    try:
        yield client
    finally:
        api.dependency_overrides.pop(get_job_client, None)


class MockPublisher(Publisher):
    """Mock publisher that records enqueued publish requests."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Create a mock publisher that records enqueued publish requests."""
        super().__init__(
            queue_timeout_seconds=0.25,
            max_attempts=3,
        )
        self.enqueued_requests: list[PublishRequest] = []

    async def put(self, request: PublishRequest) -> None:
        """Record an enqueued publish request without launching a task."""
        self.enqueued_requests.append(request)


@contextmanager
def mock_publisher(
    session_factory: async_sessionmaker[AsyncSession],
) -> Iterator[MockPublisher]:
    """Override the publisher dependency with a mock that records enqueues."""
    publisher = MockPublisher(session_factory=session_factory)
    api.dependency_overrides[get_publisher] = lambda: publisher
    try:
        yield publisher
    finally:
        api.dependency_overrides.pop(get_publisher, None)


def _set_run_status(client: TestClient, run_id: str, status: str) -> None:
    """Drive a run through an allowed status update and assert the response."""
    response = client.put(f"/api/v0/runs/{run_id}/status", json={"status": status})
    assert response.status_code == 200, response.text


def _create_completed_set(
    client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[str, str, str]:
    """Create a set that has completed its batch run and return (set_id, draft_id, batch_run_id)."""

    async def _fake_submit_job(
        self: ExternalJobClient, job_request: JobRequest
    ) -> JobAPIResponse:
        """Fake an external job submission so the worker does not drive run statuses."""
        return JobAPIResponse(external_run_id=f"external-{job_request.run_id}")

    monkeypatch.setattr(ExternalJobClient, "submit_job", _fake_submit_job)

    created = client.post(
        "/api/v0/sets", json={"model": "black-forest-labs/FLUX.2-klein-4B"}
    )
    set_id = created.json()["set_id"]
    with mock_job_client(session_factory) as job_client:
        response = client.post(
            f"/api/v0/sets/{set_id}/drafts",
            json={"prompt": f"a cat {uuid4().hex}"},
        )
    assert response.status_code == 201
    draft_id = response.json()["draft_id"]
    run_id = next(
        run["run_id"]
        for run in client.get("/api/v0/runs", params={"draft_id": draft_id}).json()[
            "runs"
        ]
    )
    assert len(job_client.enqueued_requests) == 1

    _set_run_status(client, run_id, "SUBMITTED")
    _set_run_status(client, run_id, "IN_PROGRESS")
    _set_run_status(client, run_id, "COMPLETED")

    client.patch(
        f"/api/v0/sets/{set_id}",
        json={"slug": "completed-set", "name": "Completed Set"},
    )
    commit_response = client.post(f"/api/v0/sets/{set_id}/drafts/{draft_id}/commit")
    assert commit_response.status_code == 200, commit_response.text
    assert commit_response.json()["status"] == "COMMITTED"

    runs_response = client.get("/api/v0/runs", params={"set_id": set_id})
    assert runs_response.status_code == 200
    batch_runs = [run for run in runs_response.json()["runs"] if run["type"] == "BATCH"]
    assert len(batch_runs) == 1
    batch_run_id = batch_runs[0]["run_id"]
    _set_run_status(client, batch_run_id, "SUBMITTED")
    _set_run_status(client, batch_run_id, "IN_PROGRESS")
    _set_run_status(client, batch_run_id, "COMPLETED")

    set_response = client.get(f"/api/v0/sets/{set_id}")
    assert set_response.status_code == 200
    assert set_response.json()["status"] == "COMPLETED"
    return set_id, draft_id, batch_run_id


def _get_run_id_by_type(client: TestClient, set_id: str, run_type: str) -> str:
    """Get the run id of the latest run of a given type for a set."""
    runs_response = client.get("/api/v0/runs", params={"set_id": set_id})
    assert runs_response.status_code == 200
    runs = [run for run in runs_response.json()["runs"] if run["type"] == run_type]
    assert len(runs) == 1
    return runs[0]["run_id"]


async def _get_status_events(
    session_factory: async_sessionmaker[AsyncSession], run_id: UUID
) -> list[database.RunStatusEvent]:
    """Get the status events stored for a run from the database."""
    async with session_factory() as session:
        events_table = database.RunStatusEvent.metadata.tables[
            database.RunStatusEvent.__tablename__
        ]
        stmt = select(database.RunStatusEvent).where(events_table.c.run_id == run_id)
        return list((await session.execute(stmt)).scalars().all())


def _create_set_with_draft(
    client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    prompt: str | None = None,
) -> tuple[str, str, str]:
    """Create a draft set and return (set_id, draft_id, run_id)."""
    created = client.post(
        "/api/v0/sets", json={"model": "black-forest-labs/FLUX.2-klein-4B"}
    )
    set_id = created.json()["set_id"]
    with mock_job_client(session_factory) as job_client:
        response = client.post(
            f"/api/v0/sets/{set_id}/drafts",
            json={"prompt": prompt or f"a cat {uuid4().hex}"},
        )
    assert response.status_code == 201
    draft_id = response.json()["draft_id"]
    run_id = next(
        run["run_id"]
        for run in client.get("/api/v0/runs", params={"draft_id": draft_id}).json()[
            "runs"
        ]
    )
    assert len(job_client.enqueued_requests) == 1
    enqueued = job_client.enqueued_requests[0]
    assert enqueued.job_type == database.RunType.EVALUATION
    assert enqueued.job_params.status_update_admin_run_id == enqueued.run_id
    assert enqueued.job_params.status_update_url.endswith(
        f"/runs/{enqueued.run_id}/status"
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
        body = response.json()
        assert body["status"] == "ABANDONED"


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


def test_compute_model_prompt_hash_returns_sha256_of_model_and_prompt() -> None:
    model = "black-forest-labs/FLUX.2-klein-4B"
    prompt = "a cat"
    assert (
        compute_model_prompt_hash(model, prompt)
        == hashlib.sha256(f"{model}::{prompt}".encode()).hexdigest()
    )


def test_create_draft_returns_201_with_pending_run(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with TestClient(api) as client:
        created = client.post(
            "/api/v0/sets", json={"model": "black-forest-labs/FLUX.2-klein-4B"}
        )
        set_id = created.json()["set_id"]
        with mock_job_client(session_factory) as job_client:
            response = client.post(
                f"/api/v0/sets/{set_id}/drafts",
                json={"prompt": f"a cat {uuid4().hex}"},
            )
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "PENDING"

        draft_id = body["draft_id"]
        runs_response = client.get("/api/v0/runs", params={"draft_id": draft_id})
        assert runs_response.status_code == 200
        runs = runs_response.json()["runs"]
        assert len(runs) == 1
        run = runs[0]
        assert run["status"] == "PENDING"
        assert run["type"] == "EVALUATION"
        assert run["external_run_id"] is None
        assert run["set_id"] == set_id
        assert run["draft_id"] == draft_id

        assert len(job_client.enqueued_requests) == 1
        enqueued = job_client.enqueued_requests[0]
        assert enqueued.job_type == database.RunType.EVALUATION
        assert enqueued.job_params.status_update_admin_run_id == enqueued.run_id
        assert enqueued.job_params.status_update_url.endswith(
            f"/runs/{enqueued.run_id}/status"
        )


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


def test_create_draft_with_empty_prompt_returns_422() -> None:
    with TestClient(api) as client:
        created = client.post(
            "/api/v0/sets", json={"model": "black-forest-labs/FLUX.2-klein-4B"}
        )
        set_id = created.json()["set_id"]
        response = client.post(f"/api/v0/sets/{set_id}/drafts", json={"prompt": ""})
        assert response.status_code == 422


def test_create_draft_with_long_prompt_returns_422() -> None:
    with TestClient(api) as client:
        created = client.post(
            "/api/v0/sets", json={"model": "black-forest-labs/FLUX.2-klein-4B"}
        )
        set_id = created.json()["set_id"]
        response = client.post(
            f"/api/v0/sets/{set_id}/drafts", json={"prompt": "a" * 1024}
        )
        assert response.status_code == 422


def test_create_draft_with_duplicate_prompt_returns_400(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with TestClient(api) as client:
        created = client.post(
            "/api/v0/sets", json={"model": "black-forest-labs/FLUX.2-klein-4B"}
        )
        set_id = created.json()["set_id"]
        with mock_job_client(session_factory):
            first = client.post(
                f"/api/v0/sets/{set_id}/drafts",
                json={"prompt": f"a cat {uuid4().hex}"},
            )
        assert first.status_code == 201
        with mock_job_client(session_factory):
            response = client.post(
                f"/api/v0/sets/{set_id}/drafts",
                json={"prompt": first.json()["prompt"]},
            )
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]


def test_get_draft_preview_for_missing_draft_returns_404() -> None:
    with TestClient(api) as client:
        response = client.get(f"/api/v0/sets/{uuid4()}/drafts/{uuid4()}/preview")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]


def test_get_draft_preview_requires_completed_draft_returns_400(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with TestClient(api) as client:
        created = client.post(
            "/api/v0/sets", json={"model": "black-forest-labs/FLUX.2-klein-4B"}
        )
        set_id = created.json()["set_id"]
        with mock_job_client(session_factory):
            response = client.post(
                f"/api/v0/sets/{set_id}/drafts",
                json={"prompt": f"a cat {uuid4().hex}"},
            )
        assert response.status_code == 201
        draft_id = response.json()["draft_id"]
        response = client.get(f"/api/v0/sets/{set_id}/drafts/{draft_id}/preview")
        assert response.status_code == 400
        assert "COMPLETED" in response.json()["detail"]


def test_get_draft_preview_returns_presigned_url_when_completed(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with TestClient(api) as client:
        set_id, draft_id, run_id = _create_set_with_draft(client, session_factory)
        response = client.put(
            f"/api/v0/runs/{run_id}/status", json={"status": "IN_PROGRESS"}
        )
        assert response.status_code == 200
        response = client.put(
            f"/api/v0/runs/{run_id}/status",
            json={
                "status": "COMPLETED",
                "details": {
                    "keys": [f"drafts/{draft_id}/thematic-grid-0.png"],
                    "bucket": "wrossmorrow-genai-repetitions-use1",
                },
            },
        )
        assert response.status_code == 200
        monkeypatch.setattr(
            "api.v0.handlers.drafts.create_presigned_url",
            lambda bucket, key, expires_in=300: f"https://s3.example/{bucket}/{key}",
        )
        response = client.get(f"/api/v0/sets/{set_id}/drafts/{draft_id}/preview")
        assert response.status_code == 200
        body = response.json()
        assert body["preview_url"].startswith("https://s3.example/")


def test_list_runs_returns_created_run(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with TestClient(api) as client:
        set_id, draft_id, _run_id = _create_set_with_draft(client, session_factory)
        response = client.get("/api/v0/runs", params={"draft_id": draft_id})
        assert response.status_code == 200
        body = response.json()
        assert any(r["draft_id"] == str(draft_id) for r in body["runs"])
        response = client.get("/api/v0/runs", params={"set_id": set_id})
        assert response.status_code == 200
        body = response.json()
        assert any(r["set_id"] == set_id for r in body["runs"])


def test_get_run_returns_created_run(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with TestClient(api) as client:
        _set_id, _draft_id, run_id = _create_set_with_draft(client, session_factory)
        response = client.get(f"/api/v0/runs/{run_id}")
        assert response.status_code == 200
        assert response.json()["run_id"] == run_id
        response = client.get(f"/api/v0/runs/{uuid4()}")
        assert response.status_code == 404


def test_get_run_with_invalid_uuid_returns_422() -> None:
    with TestClient(api) as client:
        response = client.get("/api/v0/runs/not-a-uuid")
        assert response.status_code == 422


def test_update_run_status_pending_to_submitted_returns_200(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with TestClient(api) as client:
        _set_id, _draft_id, run_id = _create_set_with_draft(client, session_factory)
        response = client.put(
            f"/api/v0/runs/{run_id}/status", json={"status": "SUBMITTED"}
        )
        assert response.status_code == 200
        status_response = client.get(f"/api/v0/runs/{run_id}")
        assert status_response.status_code == 200
        assert status_response.json()["status"] == "SUBMITTED"


def test_update_run_status_submitted_to_in_progress_returns_200(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with TestClient(api) as client:
        _set_id, _draft_id, run_id = _create_set_with_draft(client, session_factory)
        assert (
            client.put(
                f"/api/v0/runs/{run_id}/status", json={"status": "SUBMITTED"}
            ).status_code
            == 200
        )
        response = client.put(
            f"/api/v0/runs/{run_id}/status", json={"status": "IN_PROGRESS"}
        )
        assert response.status_code == 200
        status_response = client.get(f"/api/v0/runs/{run_id}")
        assert status_response.status_code == 200
        assert status_response.json()["status"] == "IN_PROGRESS"


def test_update_run_status_in_progress_to_completed_returns_200(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with TestClient(api) as client:
        _set_id, _draft_id, run_id = _create_set_with_draft(client, session_factory)
        assert (
            client.put(
                f"/api/v0/runs/{run_id}/status", json={"status": "SUBMITTED"}
            ).status_code
            == 200
        )
        assert (
            client.put(
                f"/api/v0/runs/{run_id}/status", json={"status": "IN_PROGRESS"}
            ).status_code
            == 200
        )
        response = client.put(
            f"/api/v0/runs/{run_id}/status", json={"status": "COMPLETED"}
        )
        assert response.status_code == 200
        status_response = client.get(f"/api/v0/runs/{run_id}")
        assert status_response.status_code == 200
        assert status_response.json()["status"] == "COMPLETED"


def test_update_run_status_pending_to_failed_returns_200(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with TestClient(api) as client:
        set_id, draft_id, run_id = _create_set_with_draft(client, session_factory)
        response = client.put(
            f"/api/v0/runs/{run_id}/status", json={"status": "FAILED"}
        )
        assert response.status_code == 200
        draft_response = client.get(f"/api/v0/sets/{set_id}/drafts/{draft_id}")
        assert draft_response.status_code == 200
        assert draft_response.json()["status"] == "FAILED"


def test_update_run_status_same_state_returns_200_noop(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with TestClient(api) as client:
        _set_id, _draft_id, run_id = _create_set_with_draft(client, session_factory)
        response = client.put(
            f"/api/v0/runs/{run_id}/status", json={"status": "SUBMITTED"}
        )
        assert response.status_code == 200
        response = client.put(
            f"/api/v0/runs/{run_id}/status", json={"status": "SUBMITTED"}
        )
        assert response.status_code == 200
        status_response = client.get(f"/api/v0/runs/{run_id}")
        assert status_response.status_code == 200
        assert status_response.json()["status"] == "SUBMITTED"


def test_update_run_status_invalid_transition_returns_400(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with TestClient(api) as client:
        _set_id, _draft_id, run_id = _create_set_with_draft(client, session_factory)
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


def test_update_run_status_with_message_and_details_returns_200(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with TestClient(api) as client:
        _set_id, _draft_id, run_id = _create_set_with_draft(client, session_factory)
        response = client.put(
            f"/api/v0/runs/{run_id}/status",
            json={
                "status": "FAILED",
                "message": "mock external job failed",
                "details": {"error": "job crashed"},
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "FAILED"
        assert body["message"] == "mock external job failed"
        assert body["details"] == {"error": "job crashed"}


def test_update_run_status_without_message_and_details_returns_200(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with TestClient(api) as client:
        _set_id, _draft_id, run_id = _create_set_with_draft(client, session_factory)
        response = client.put(
            f"/api/v0/runs/{run_id}/status", json={"status": "FAILED"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "FAILED"
        assert body["message"] is None
        assert body["details"] is None


def test_update_run_status_with_non_string_message_returns_422(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with TestClient(api) as client:
        _set_id, _draft_id, run_id = _create_set_with_draft(client, session_factory)
        response = client.put(
            f"/api/v0/runs/{run_id}/status",
            json={"status": "IN_PROGRESS", "message": 123},
        )
        assert response.status_code == 422


def test_update_run_status_with_non_json_details_returns_422(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with TestClient(api) as client:
        _set_id, _draft_id, run_id = _create_set_with_draft(client, session_factory)
        response = client.put(
            f"/api/v0/runs/{run_id}/status",
            json={"status": "IN_PROGRESS", "details": "not-an-object"},
        )
        assert response.status_code == 422


def test_update_run_status_records_full_payload_as_status_event(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Updating a run status stores the received payload as a status event."""
    with TestClient(api) as client:
        _set_id, _draft_id, run_id = _create_set_with_draft(client, session_factory)
        response = client.put(
            f"/api/v0/runs/{run_id}/status",
            json={
                "status": "IN_PROGRESS",
                "message": "external job started",
                "details": {"phase": "IN_PROGRESS"},
            },
        )
        assert response.status_code == 200, response.text

    events = asyncio.run(_get_status_events(session_factory, UUID(run_id)))
    assert len(events) == 1
    event = events[0]
    assert event.run_id == UUID(run_id)
    assert event.status == database.RunStatus.IN_PROGRESS
    assert event.message == "external job started"
    assert event.details == {"phase": "IN_PROGRESS"}
    assert event.received_at is not None


def test_update_run_status_invalid_transition_does_not_record_status_event(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Updating a run status with an invalid transition does not record an event."""
    with TestClient(api) as client:
        _set_id, _draft_id, run_id = _create_set_with_draft(client, session_factory)
        response = client.put(
            f"/api/v0/runs/{run_id}/status", json={"status": "COMPLETED"}
        )
        assert response.status_code == 400
        assert "Invalid run status transition" in response.json()["detail"]

    events = asyncio.run(_get_status_events(session_factory, UUID(run_id)))
    assert len(events) == 0


def test_list_run_status_events_returns_stored_events(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Listing run status events returns the stored status update payloads."""
    with TestClient(api) as client:
        _set_id, _draft_id, run_id = _create_set_with_draft(client, session_factory)
        assert (
            client.put(
                f"/api/v0/runs/{run_id}/status",
                json={
                    "status": "IN_PROGRESS",
                    "message": "external job started",
                    "details": {"phase": "IN_PROGRESS"},
                },
            ).status_code
            == 200
        )
        assert (
            client.put(
                f"/api/v0/runs/{run_id}/status",
                json={"status": "COMPLETED"},
            ).status_code
            == 200
        )
        response = client.get(f"/api/v0/runs/{run_id}/events")
        assert response.status_code == 200, response.text
        body = response.json()
        assert len(body["events"]) == 2
        assert {event["status"] for event in body["events"]} == {
            "IN_PROGRESS",
            "COMPLETED",
        }
        for event in body["events"]:
            assert event["run_id"] == run_id
            assert event["received_at"]


def test_list_run_status_events_for_unknown_run_returns_404() -> None:
    """Listing status events for an unknown run returns 404."""
    with TestClient(api) as client:
        response = client.get(f"/api/v0/runs/{uuid4()}/events")
        assert response.status_code == 404


def test_update_run_status_failed_propagates_to_draft_returns_200(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with TestClient(api) as client:
        set_id, draft_id, run_id = _create_set_with_draft(client, session_factory)
        response = client.put(
            f"/api/v0/runs/{run_id}/status", json={"status": "FAILED"}
        )
        assert response.status_code == 200
        draft_response = client.get(f"/api/v0/sets/{set_id}/drafts/{draft_id}")
        assert draft_response.status_code == 200
        assert draft_response.json()["status"] == "FAILED"


def test_update_run_status_failed_batch_run_marks_set_failed(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with TestClient(api) as client:
        set_id, draft_id, run_id = _create_set_with_draft(client, session_factory)
        client.patch(
            f"/api/v0/sets/{set_id}",
            json={"slug": "batch-failed-set", "name": "Batch Failed Set"},
        )
        assert (
            client.put(
                f"/api/v0/runs/{run_id}/status", json={"status": "SUBMITTED"}
            ).status_code
            == 200
        )
        assert (
            client.put(
                f"/api/v0/runs/{run_id}/status", json={"status": "IN_PROGRESS"}
            ).status_code
            == 200
        )
        assert (
            client.put(
                f"/api/v0/runs/{run_id}/status", json={"status": "COMPLETED"}
            ).status_code
            == 200
        )
        with mock_job_client(session_factory) as job_client:
            commit_response = client.post(
                f"/api/v0/sets/{set_id}/drafts/{draft_id}/commit"
            )
        assert commit_response.status_code == 200
        assert commit_response.json()["status"] == "COMMITTED"
        runs_response = client.get("/api/v0/runs", params={"set_id": set_id})
        assert runs_response.status_code == 200
        batch_runs = [
            run for run in runs_response.json()["runs"] if run["type"] == "BATCH"
        ]
        assert len(batch_runs) == 1
        batch_run_id = batch_runs[0]["run_id"]
        assert batch_run_id != run_id
        assert job_client.enqueued_requests[0].job_type == database.RunType.BATCH

        response = client.put(
            f"/api/v0/runs/{batch_run_id}/status", json={"status": "FAILED"}
        )
        assert response.status_code == 200
        set_response = client.get(f"/api/v0/sets/{set_id}")
        assert set_response.status_code == 200
        assert set_response.json()["status"] == "FAILED"
        draft_response = client.get(f"/api/v0/sets/{set_id}/drafts/{draft_id}")
        assert draft_response.status_code == 200
        assert draft_response.json()["status"] == "COMMITTED"


def test_redo_run_requires_failed_status_returns_400(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with TestClient(api) as client:
        _set_id, _draft_id, run_id = _create_set_with_draft(client, session_factory)
        response = client.post(f"/api/v0/runs/{run_id}")
        assert response.status_code == 400
        assert "FAILED" in response.json()["detail"]


def test_redo_run_returns_new_run_returns_201(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with TestClient(api) as client:
        _set_id, _draft_id, run_id = _create_set_with_draft(client, session_factory)
        assert (
            client.put(
                f"/api/v0/runs/{run_id}/status", json={"status": "FAILED"}
            ).status_code
            == 200
        )
        with mock_job_client(session_factory):
            response = client.post(f"/api/v0/runs/{run_id}")
        assert response.status_code == 201
        new_run_id = response.json()["run_id"]
        new_run_response = client.get(f"/api/v0/runs/{new_run_id}")
        assert new_run_response.status_code == 200
        assert new_run_response.json()["status"] == "PENDING"
        assert new_run_response.json()["external_run_id"] is None


def test_commit_draft_returns_200_and_commits_set(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with TestClient(api) as client:
        set_id, draft_id, run_id = _create_set_with_draft(client, session_factory)
        client.patch(
            f"/api/v0/sets/{set_id}",
            json={"slug": "commit-set-abc", "name": "Commit Set"},
        )
        assert (
            client.put(
                f"/api/v0/runs/{run_id}/status", json={"status": "SUBMITTED"}
            ).status_code
            == 200
        )
        assert (
            client.put(
                f"/api/v0/runs/{run_id}/status", json={"status": "IN_PROGRESS"}
            ).status_code
            == 200
        )
        assert (
            client.put(
                f"/api/v0/runs/{run_id}/status", json={"status": "COMPLETED"}
            ).status_code
            == 200
        )
        response = client.post(f"/api/v0/sets/{set_id}/drafts/{draft_id}/commit")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "COMMITTED"
        set_response = client.get(f"/api/v0/sets/{set_id}")
        assert set_response.status_code == 200
        assert set_response.json()["status"] == "COMMITTED"

        model = set_response.json()["model"]
        prompt = set_response.json()["prompt"]
        assert set_response.json()["model_prompt_hash"] == compute_model_prompt_hash(
            model, prompt
        )


def test_commit_draft_with_draft_not_completed_returns_400(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with TestClient(api) as client:
        set_id, draft_id, _run_id = _create_set_with_draft(client, session_factory)
        client.patch(
            f"/api/v0/sets/{set_id}",
            json={"slug": "commit-set-abc", "name": "Commit Set"},
        )
        response = client.post(f"/api/v0/sets/{set_id}/drafts/{draft_id}/commit")
        assert response.status_code == 400
        assert "COMPLETED" in response.json()["detail"]


def test_commit_draft_with_missing_slug_and_name_returns_400(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with TestClient(api) as client:
        created = client.post(
            "/api/v0/sets", json={"model": "black-forest-labs/FLUX.2-klein-4B"}
        )
        set_id = created.json()["set_id"]
        with mock_job_client(session_factory):
            response = client.post(
                f"/api/v0/sets/{set_id}/drafts",
                json={"prompt": f"a cat {uuid4().hex}"},
            )
        assert response.status_code == 201
        draft_id = response.json()["draft_id"]
        response = client.post(f"/api/v0/sets/{set_id}/drafts/{draft_id}/commit")
        assert response.status_code == 400
        assert "slug and name" in response.json()["detail"]


def test_create_draft_with_failing_job_returns_500(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with TestClient(api) as client:
        created = client.post(
            "/api/v0/sets", json={"model": "black-forest-labs/FLUX.2-klein-4B"}
        )
        set_id = created.json()["set_id"]
        api.dependency_overrides[get_job_client] = lambda: FailingExternalJobClient(
            session_factory=session_factory
        )
        try:
            response = client.post(
                f"/api/v0/sets/{set_id}/drafts",
                json={"prompt": f"a cat {uuid4().hex}"},
            )
        finally:
            api.dependency_overrides.pop(get_job_client, None)
        assert response.status_code == 500


def test_publish_set_returns_200_and_enqueues_publish_run(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Publishing a COMPLETED set returns 200 and enqueues a publish run."""
    with TestClient(api) as client:
        set_id, draft_id, batch_run_id = _create_completed_set(
            client, session_factory, monkeypatch
        )
        with mock_publisher(session_factory) as publisher:
            response = client.post(f"/api/v0/sets/{set_id}/publish")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "PUBLISHING"
        assert len(publisher.enqueued_requests) == 1
        enqueued = publisher.enqueued_requests[0]
        assert str(enqueued.set_id) == set_id
        assert str(enqueued.draft_id) == draft_id
        assert str(enqueued.run_id) != batch_run_id
        assert enqueued.attempts == 0


def test_publish_set_not_completed_returns_400() -> None:
    """Publishing a set that is not COMPLETED returns 400."""
    with TestClient(api) as client:
        created = client.post(
            "/api/v0/sets", json={"model": "black-forest-labs/FLUX.2-klein-4B"}
        )
        set_id = created.json()["set_id"]
        response = client.post(f"/api/v0/sets/{set_id}/publish")
        assert response.status_code == 400
        assert "COMPLETED" in response.json()["detail"]


def test_publish_set_not_found_returns_404() -> None:
    """Publishing a missing set returns 404."""
    with TestClient(api) as client:
        response = client.post(f"/api/v0/sets/{uuid4()}/publish")
        assert response.status_code == 404


def test_update_run_status_publish_completed_marks_set_published(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A completed publish run marks the set PUBLISHED and stamps published_at."""
    with TestClient(api) as client:
        set_id, _draft_id, _batch_run_id = _create_completed_set(
            client, session_factory, monkeypatch
        )
        with mock_publisher(session_factory):
            response = client.post(f"/api/v0/sets/{set_id}/publish")
        assert response.status_code == 200, response.text
        publish_run_id = _get_run_id_by_type(client, set_id, "PUBLISH")

        assert (
            client.put(
                f"/api/v0/runs/{publish_run_id}/status", json={"status": "IN_PROGRESS"}
            ).status_code
            == 200
        )
        assert (
            client.put(
                f"/api/v0/runs/{publish_run_id}/status", json={"status": "COMPLETED"}
            ).status_code
            == 200
        )
        set_response = client.get(f"/api/v0/sets/{set_id}")
        assert set_response.status_code == 200
        assert set_response.json()["status"] == "PUBLISHED"
        assert set_response.json()["published_at"]


def test_update_run_status_publish_failed_marks_set_failed(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed publish run marks the set FAILED."""
    with TestClient(api) as client:
        set_id, _draft_id, _batch_run_id = _create_completed_set(
            client, session_factory, monkeypatch
        )
        with mock_publisher(session_factory):
            response = client.post(f"/api/v0/sets/{set_id}/publish")
        assert response.status_code == 200, response.text
        publish_run_id = _get_run_id_by_type(client, set_id, "PUBLISH")

        assert (
            client.put(
                f"/api/v0/runs/{publish_run_id}/status", json={"status": "FAILED"}
            ).status_code
            == 200
        )
        set_response = client.get(f"/api/v0/sets/{set_id}")
        assert set_response.status_code == 200
        assert set_response.json()["status"] == "FAILED"
        assert set_response.json()["published_at"] is None


def test_update_run_status_publish_invalid_transition_returns_400(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Updating a publish run status without a valid transition returns 400."""
    with TestClient(api) as client:
        set_id, _draft_id, _batch_run_id = _create_completed_set(
            client, session_factory, monkeypatch
        )
        with mock_publisher(session_factory):
            response = client.post(f"/api/v0/sets/{set_id}/publish")
        assert response.status_code == 200, response.text
        publish_run_id = _get_run_id_by_type(client, set_id, "PUBLISH")

        response = client.put(
            f"/api/v0/runs/{publish_run_id}/status", json={"status": "COMPLETED"}
        )
        assert response.status_code == 400
        assert "Invalid run status transition" in response.json()["detail"]
        assert client.get(f"/api/v0/sets/{set_id}").json()["status"] == "PUBLISHING"
