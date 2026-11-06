"""Integration tests for the Unending Admin API against a live server."""

import os
import time
from typing import Any
from uuid import uuid4

import httpx
import pytest

DEFAULT_MODEL = "black-forest-labs/FLUX.2-klein-4B"
DEFAULT_PROMPT = "a cat"


@pytest.fixture
def http_client() -> httpx.Client:
    """HTTP client bound to the admin API base URL from the environment."""
    base_url = os.environ.get("ADMIN_API_BASE_URL", "http://localhost:8000")
    return httpx.Client(base_url=base_url, timeout=10.0)


@pytest.fixture(scope="session", autouse=True)
def skip_without_live_server() -> None:
    """Skip the integration suite when no live admin API server is reachable."""
    base_url = os.environ.get("ADMIN_API_BASE_URL", "http://localhost:8000")
    with httpx.Client(base_url=base_url, timeout=10.0) as client:
        try:
            response = client.get("/health/alive")
        except httpx.HTTPError:
            pytest.skip(f"Admin API live server not reachable at {base_url}.")
        if response.status_code != 200:
            pytest.skip(f"Admin API live server at {base_url} is not healthy.")


def _unique_slug() -> str:
    """Generate a unique set slug that satisfies the API slug pattern."""
    return f"it-{uuid4().hex[:8]}a"


def _unique_prompt() -> str:
    """Generate a unique draft prompt that satisfies the API prompt constraints."""
    return f"a cat {uuid4().hex}"


def _get_run(http_client: httpx.Client, run_id: str) -> dict[str, Any]:
    """Get a run by id and return its body."""
    response = http_client.get(f"/api/v0/runs/{run_id}")
    assert response.status_code == 200, response.text
    return response.json()


def _wait_for_run_status(
    http_client: httpx.Client, run_id: str, status: str, timeout: float = 30.0
) -> dict[str, Any]:
    """Poll a run until it reaches the given status."""
    deadline = time.monotonic() + timeout
    run = _get_run(http_client, run_id)
    while run["status"] != status:
        assert time.monotonic() < deadline, (
            f"Timed out waiting for run status {status}."
        )
        time.sleep(0.25)
        run = _get_run(http_client, run_id)
    return run


def _create_set(
    client: httpx.Client,
    slug: str | None = None,
    name: str | None = None,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """Create a set and return its response body."""
    body: dict[str, Any] = {"model": model}
    if slug is not None:
        body["slug"] = slug
    if name is not None:
        body["name"] = name
    response = client.post("/api/v0/sets", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _patch_set(
    client: httpx.Client, set_id: str, slug: str, name: str
) -> dict[str, Any]:
    """Patch a draft set's slug and name and return the updated body."""
    response = client.patch(f"/api/v0/sets/{set_id}", json={"slug": slug, "name": name})
    assert response.status_code == 200, response.text
    return response.json()


def _create_draft(
    client: httpx.Client, set_id: str, prompt: str = DEFAULT_PROMPT
) -> dict[str, Any]:
    """Create a set draft (which triggers an external job) and return the draft body."""
    response = client.post(f"/api/v0/sets/{set_id}/drafts", json={"prompt": prompt})
    assert response.status_code == 201, response.text
    return response.json()


def _get_draft(client: httpx.Client, set_id: str, draft_id: str) -> dict[str, Any]:
    """Get a set draft and return its body."""
    response = client.get(f"/api/v0/sets/{set_id}/drafts/{draft_id}")
    assert response.status_code == 200, response.text
    return response.json()


def _get_run_id_by_type(client: httpx.Client, set_id: str, run_type: str) -> str:
    """Get the run id of the run of a given type for a set."""
    response = client.get("/api/v0/runs", params={"set_id": set_id})
    assert response.status_code == 200, response.text
    runs = [run for run in response.json()["runs"] if run["type"] == run_type]
    assert len(runs) == 1
    return runs[0]["run_id"]


def _get_run_by_draft(client: httpx.Client, draft_id: str) -> dict[str, Any]:
    """Get the run created for a draft and return its body."""
    response = client.get("/api/v0/runs", params={"draft_id": draft_id})
    assert response.status_code == 200, response.text
    runs = response.json()["runs"]
    assert len(runs) > 0
    return runs[0]


def _update_run_status(
    client: httpx.Client,
    run_id: str,
    status: str,
    message: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Update a run status and return the updated run body."""
    body: dict[str, Any] = {"status": status}
    if message is not None:
        body["message"] = message
    if details is not None:
        body["details"] = details
    response = client.put(f"/api/v0/runs/{run_id}/status", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def _commit_draft(client: httpx.Client, set_id: str, draft_id: str) -> dict[str, Any]:
    """Commit a draft set and return the committed set body."""
    response = client.post(f"/api/v0/sets/{set_id}/drafts/{draft_id}/commit")
    assert response.status_code == 200, response.text
    return response.json()


def test_health_alive(http_client: httpx.Client) -> None:
    """Liveness probe returns 200 with an alive status."""
    response = http_client.get("/health/alive")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_health_ready(http_client: httpx.Client) -> None:
    """Readiness probe returns 200 with a ready status."""
    response = http_client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_list_sets(http_client: httpx.Client) -> None:
    """List sets returns a 200 with a sets collection."""
    response = http_client.get("/api/v0/sets")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    assert "sets" in body


def test_create_set_returns_201_with_draft_status(http_client: httpx.Client) -> None:
    """Creating a set returns 201 with a DRAFT status and no prompt yet."""
    body = _create_set(http_client)
    assert body["status"] == "DRAFT"
    assert body["model"] == DEFAULT_MODEL
    assert body["prompt"] is None
    assert body["set_id"]


def test_get_set_returns_created_set(http_client: httpx.Client) -> None:
    """Getting a created set returns 200 with the same set; unknown sets 404."""
    body = _create_set(http_client, slug=_unique_slug(), name="It Get Set")
    set_id = body["set_id"]
    response = http_client.get(f"/api/v0/sets/{set_id}")
    assert response.status_code == 200
    assert response.json()["set_id"] == set_id
    assert response.json()["status"] == "DRAFT"
    response = http_client.get(f"/api/v0/sets/{uuid4()}")
    assert response.status_code == 404


def test_patch_set_updates_slug_and_name(http_client: httpx.Client) -> None:
    """Patching a draft set updates the slug and name."""
    body = _create_set(http_client)
    set_id = body["set_id"]
    slug = _unique_slug()
    updated = _patch_set(http_client, set_id, slug=slug, name="It Patched Set")
    assert updated["slug"] == slug
    assert updated["name"] == "It Patched Set"
    assert updated["status"] == "DRAFT"


def test_delete_set_marks_abandoned(http_client: httpx.Client) -> None:
    """Deleting a draft set marks it ABANDONED."""
    body = _create_set(http_client)
    set_id = body["set_id"]
    response = http_client.delete(f"/api/v0/sets/{set_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "ABANDONED"


def test_create_draft_returns_201_with_pending_run(http_client: httpx.Client) -> None:
    """Creating a draft returns 201 with a PENDING draft and an EVALUATION run."""
    set_body = _create_set(http_client)
    set_id = set_body["set_id"]
    draft = _create_draft(http_client, set_id, prompt=_unique_prompt())
    draft_id = draft["draft_id"]
    run = _get_run_by_draft(http_client, draft_id)
    submitted_run = _wait_for_run_status(http_client, run["run_id"], "SUBMITTED")
    assert submitted_run["status"] == "SUBMITTED"
    assert submitted_run["type"] == "EVALUATION"
    assert submitted_run["external_run_id"]
    assert submitted_run["set_id"] == set_id
    assert submitted_run["draft_id"] == draft_id


def test_create_draft_on_missing_set_returns_404(http_client: httpx.Client) -> None:
    """Creating a draft on a missing set returns 404."""
    response = http_client.post(
        f"/api/v0/sets/{uuid4()}/drafts", json={"prompt": DEFAULT_PROMPT}
    )
    assert response.status_code == 404


def test_create_draft_on_abandoned_set_returns_400(http_client: httpx.Client) -> None:
    """Creating a draft on a set that is not DRAFT returns 400."""
    set_body = _create_set(http_client)
    set_id = set_body["set_id"]
    assert http_client.delete(f"/api/v0/sets/{set_id}").status_code == 200
    response = http_client.post(
        f"/api/v0/sets/{set_id}/drafts", json={"prompt": DEFAULT_PROMPT}
    )
    assert response.status_code == 400


def test_create_draft_with_empty_prompt_returns_422(http_client: httpx.Client) -> None:
    """Creating a draft with an empty prompt returns 422."""
    set_body = _create_set(http_client)
    response = http_client.post(
        f"/api/v0/sets/{set_body['set_id']}/drafts", json={"prompt": ""}
    )
    assert response.status_code == 422


def test_create_draft_with_long_prompt_returns_422(http_client: httpx.Client) -> None:
    """Creating a draft with a prompt longer than 1023 characters returns 422."""
    set_body = _create_set(http_client)
    response = http_client.post(
        f"/api/v0/sets/{set_body['set_id']}/drafts", json={"prompt": "a" * 1024}
    )
    assert response.status_code == 422


def test_create_draft_with_duplicate_prompt_returns_400(
    http_client: httpx.Client,
) -> None:
    """Creating a draft with a prompt that was already used returns 400."""
    set_body = _create_set(http_client)
    first_draft = _create_draft(
        http_client, set_body["set_id"], prompt=_unique_prompt()
    )
    response = http_client.post(
        f"/api/v0/sets/{set_body['set_id']}/drafts",
        json={"prompt": first_draft["prompt"]},
    )
    assert response.status_code == 400


def test_full_flow_draft_to_committed_batch_to_completed(
    http_client: httpx.Client,
) -> None:
    """Full flow: create set, draft, drive evaluation run, commit, drive batch run."""
    set_body = _create_set(http_client, slug=_unique_slug(), name="It Flow Set")
    set_id = set_body["set_id"]
    prompt = _unique_prompt()
    draft = _create_draft(http_client, set_id, prompt=prompt)
    draft_id = draft["draft_id"]
    run = _get_run_by_draft(http_client, draft_id)
    run_id = run["run_id"]

    assert (
        _update_run_status(http_client, run_id, "IN_PROGRESS")["status"]
        == "IN_PROGRESS"
    )
    assert _get_draft(http_client, set_id, draft_id)["status"] == "IN_PROGRESS"
    assert _update_run_status(http_client, run_id, "COMPLETED")["status"] == "COMPLETED"
    assert _get_draft(http_client, set_id, draft_id)["status"] == "COMPLETED"

    committed = _commit_draft(http_client, set_id, draft_id)
    assert committed["status"] == "COMMITTED"
    committed_set = http_client.get(f"/api/v0/sets/{set_id}").json()
    assert committed_set["status"] == "COMMITTED"
    assert committed_set["prompt"] == prompt
    assert committed_set["post_date"]
    assert committed_set["committed_at"]

    runs_response = http_client.get("/api/v0/runs", params={"set_id": set_id})
    assert runs_response.status_code == 200
    batch_runs = [run for run in runs_response.json()["runs"] if run["type"] == "BATCH"]
    assert len(batch_runs) == 1
    batch_run = batch_runs[0]
    batch_run = _wait_for_run_status(http_client, batch_run["run_id"], "SUBMITTED")

    assert _update_run_status(http_client, batch_run["run_id"], "IN_PROGRESS")[
        "status"
    ] == ("IN_PROGRESS")
    assert _update_run_status(http_client, batch_run["run_id"], "COMPLETED")[
        "status"
    ] == ("COMPLETED")
    completed_set = http_client.get(f"/api/v0/sets/{set_id}").json()
    assert completed_set["status"] == "COMPLETED"


def test_full_flow_draft_to_committed_batch_to_completed_to_published(
    http_client: httpx.Client,
) -> None:
    """Full flow: create set, draft, drive evaluation run, commit, drive batch run, publish."""
    set_body = _create_set(http_client, slug=_unique_slug(), name="It Flow Publish Set")
    set_id = set_body["set_id"]
    prompt = _unique_prompt()
    draft = _create_draft(http_client, set_id, prompt=prompt)
    draft_id = draft["draft_id"]
    run = _get_run_by_draft(http_client, draft_id)
    run_id = run["run_id"]

    assert (
        _update_run_status(http_client, run_id, "IN_PROGRESS")["status"]
        == "IN_PROGRESS"
    )
    assert _get_draft(http_client, set_id, draft_id)["status"] == "IN_PROGRESS"
    assert _update_run_status(http_client, run_id, "COMPLETED")["status"] == "COMPLETED"
    assert _get_draft(http_client, set_id, draft_id)["status"] == "COMPLETED"

    committed = _commit_draft(http_client, set_id, draft_id)
    assert committed["status"] == "COMMITTED"
    committed_set = http_client.get(f"/api/v0/sets/{set_id}").json()
    assert committed_set["status"] == "COMMITTED"
    assert committed_set["prompt"] == prompt
    assert committed_set["post_date"]
    assert committed_set["committed_at"]

    runs_response = http_client.get("/api/v0/runs", params={"set_id": set_id})
    assert runs_response.status_code == 200
    batch_runs = [run for run in runs_response.json()["runs"] if run["type"] == "BATCH"]
    assert len(batch_runs) == 1
    batch_run = batch_runs[0]
    batch_run = _wait_for_run_status(http_client, batch_run["run_id"], "SUBMITTED")

    assert _update_run_status(http_client, batch_run["run_id"], "IN_PROGRESS")[
        "status"
    ] == ("IN_PROGRESS")
    assert _update_run_status(http_client, batch_run["run_id"], "COMPLETED")[
        "status"
    ] == ("COMPLETED")
    completed_set = http_client.get(f"/api/v0/sets/{set_id}").json()
    assert completed_set["status"] == "COMPLETED"

    publish_response = http_client.post(f"/api/v0/sets/{set_id}/publish")
    assert publish_response.status_code == 200, publish_response.text
    assert publish_response.json()["status"] == "PUBLISHING"

    publish_run_id = _get_run_id_by_type(http_client, set_id, "PUBLISH")
    assert (
        _update_run_status(http_client, publish_run_id, "IN_PROGRESS")["status"]
        == "IN_PROGRESS"
    )
    assert (
        _update_run_status(http_client, publish_run_id, "COMPLETED")["status"]
        == "COMPLETED"
    )
    published_set = http_client.get(f"/api/v0/sets/{set_id}").json()
    assert published_set["status"] == "PUBLISHED"
    assert published_set["published_at"]


def test_commit_draft_with_draft_not_completed_returns_400(
    http_client: httpx.Client,
) -> None:
    """Committing a draft that is not COMPLETED returns 400."""
    set_body = _create_set(
        http_client, slug=_unique_slug(), name="It Commit Pending Set"
    )
    draft = _create_draft(http_client, set_body["set_id"], prompt=_unique_prompt())
    response = http_client.post(
        f"/api/v0/sets/{set_body['set_id']}/drafts/{draft['draft_id']}/commit"
    )
    assert response.status_code == 400
    assert "COMPLETED" in response.json()["detail"]


def test_commit_draft_with_missing_slug_and_name_returns_400(
    http_client: httpx.Client,
) -> None:
    """Committing a draft without a set slug and name returns 400."""
    set_body = _create_set(http_client)
    draft = _create_draft(http_client, set_body["set_id"], prompt=_unique_prompt())
    response = http_client.post(
        f"/api/v0/sets/{set_body['set_id']}/drafts/{draft['draft_id']}/commit"
    )
    assert response.status_code == 400
    assert "slug and name" in response.json()["detail"]


def test_update_run_status_with_message_and_details_returns_200(
    http_client: httpx.Client,
) -> None:
    """Updating a run status with a message and JSON details returns the run."""
    set_body = _create_set(http_client)
    draft = _create_draft(http_client, set_body["set_id"], prompt=_unique_prompt())
    run = _get_run_by_draft(http_client, draft["draft_id"])

    updated = _update_run_status(
        http_client,
        run["run_id"],
        "FAILED",
        message="mock external job failed",
        details={"error": "job crashed"},
    )
    assert updated["status"] == "FAILED"
    assert updated["message"] == "mock external job failed"
    assert updated["details"] == {"error": "job crashed"}


def test_update_run_status_invalid_transition_returns_400(
    http_client: httpx.Client,
) -> None:
    """Updating a run status without a valid transition returns 400."""
    set_body = _create_set(http_client)
    draft = _create_draft(http_client, set_body["set_id"], prompt=_unique_prompt())
    run = _get_run_by_draft(http_client, draft["draft_id"])
    response = http_client.put(
        f"/api/v0/runs/{run['run_id']}/status", json={"status": "COMPLETED"}
    )
    assert response.status_code == 400
    assert "Invalid run status transition" in response.json()["detail"]


def test_update_run_status_not_found_returns_404(http_client: httpx.Client) -> None:
    """Updating the status of an unknown run returns 404."""
    response = http_client.put(
        f"/api/v0/runs/{uuid4()}/status", json={"status": "IN_PROGRESS"}
    )
    assert response.status_code == 404


def test_redo_run_returns_new_run_returns_201(http_client: httpx.Client) -> None:
    """Redoing a failed run creates a new run in PENDING status."""
    set_body = _create_set(http_client)
    draft = _create_draft(http_client, set_body["set_id"], prompt=_unique_prompt())
    run = _get_run_by_draft(http_client, draft["draft_id"])
    assert (
        _update_run_status(http_client, run["run_id"], "FAILED")["status"] == "FAILED"
    )
    assert (
        _get_draft(http_client, set_body["set_id"], draft["draft_id"])["status"]
        == "FAILED"
    )

    response = http_client.post(f"/api/v0/runs/{run['run_id']}")
    assert response.status_code == 201
    new_run = response.json()
    assert new_run["status"] == "PENDING"
    assert new_run["external_run_id"] is None
    assert new_run["type"] == run["type"]
    assert new_run["run_id"] != run["run_id"]

    assert _update_run_status(http_client, new_run["run_id"], "IN_PROGRESS")[
        "status"
    ] == ("IN_PROGRESS")
    assert _update_run_status(http_client, new_run["run_id"], "COMPLETED")[
        "status"
    ] == ("COMPLETED")
    assert (
        _get_draft(http_client, set_body["set_id"], draft["draft_id"])["status"]
        == "COMPLETED"
    )
