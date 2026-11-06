"""Unit tests for the publish worker queue."""

import asyncio
import contextlib
import time
from collections.abc import Callable
from uuid import uuid4

import boto3  # type: ignore[import-untyped]
import pytest

from api.settings import settings
from api.utils.publish import Publisher, PublishRequest


class MockEcsClient:
    """Mock ECS client that controls task launch outcomes."""

    def __init__(
        self, fail_times: int = 0, fail_responses: list[dict] | None = None
    ) -> None:
        """Create a mock ECS client that fails task launches on purpose."""
        self.fail_times = fail_times
        self.fail_responses = list(fail_responses or [])
        self.failures_remaining = fail_times
        self.run_task_calls: list[dict] = []

    def run_task(self, **kwargs: dict) -> dict:
        """Record the task launch and optionally fail it like ECS would."""
        self.run_task_calls.append(kwargs)
        if self.failures_remaining > 0:
            self.failures_remaining -= 1
            if self.fail_responses:
                return {"failures": list(self.fail_responses), "tasks": []}
            raise RuntimeError("mock ECS task launch failure")
        return {
            "failures": [],
            "tasks": [
                {
                    "taskArn": f"arn:aws:ecs:us-east-1:123456789012:task/publish/{uuid4()}"
                },
            ],
        }


async def _wait_for_condition(
    condition: Callable[[], bool], timeout: float = 5.0
) -> None:
    """Poll a condition until it holds or the timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("Timed out waiting for the condition to hold.")


async def _run_publisher_until(
    publisher: Publisher,
    mock_ecs: MockEcsClient,
    request: PublishRequest,
    expected_calls: int,
) -> None:
    """Start the publisher worker, enqueue a request, and wait for the launches."""
    task = asyncio.create_task(publisher.run())
    try:
        await publisher.put(request)
        await _wait_for_condition(
            lambda: len(mock_ecs.run_task_calls) >= expected_calls
        )
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await publisher.aclose()


def _publish_request() -> PublishRequest:
    """Build a publish request for a fresh run."""
    return PublishRequest(set_id=uuid4(), draft_id=uuid4(), run_id=uuid4())


def test_publisher_submits_ecs_task_and_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The publish worker launches one Fargate task and records the task arn."""

    mock_ecs = MockEcsClient()

    async def scenario() -> None:
        monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: mock_ecs)
        publisher = Publisher(queue_timeout_seconds=0.25, max_attempts=3)
        await _run_publisher_until(
            publisher, mock_ecs, _publish_request(), expected_calls=1
        )

    asyncio.run(scenario())
    assert len(mock_ecs.run_task_calls) == 1
    kwargs = mock_ecs.run_task_calls[0]
    assert kwargs["cluster"] == settings.publish_ecs_cluster
    assert kwargs["taskDefinition"] == settings.publish_task_family
    assert kwargs["launchType"] == "FARGATE"
    assert kwargs["count"] == 1
    override = kwargs["overrides"]["containerOverrides"][0]
    assert override["name"] == settings.publish_container
    assert override["command"][0] == "publish"
    assert override["command"][1] == "--batch-run-id"


def test_publisher_retries_failed_task_launches_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The publish worker retries a failed task launch until it succeeds."""

    mock_ecs = MockEcsClient(fail_times=1)

    async def scenario() -> None:
        monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: mock_ecs)
        publisher = Publisher(queue_timeout_seconds=0.25, max_attempts=3)
        await _run_publisher_until(
            publisher, mock_ecs, _publish_request(), expected_calls=2
        )

    asyncio.run(scenario())
    assert len(mock_ecs.run_task_calls) == 2
    assert mock_ecs.run_task_calls[0]["cluster"] == settings.publish_ecs_cluster
    assert mock_ecs.run_task_calls[1]["cluster"] == settings.publish_ecs_cluster


def test_publisher_retries_on_ecs_launch_failures_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The publish worker retries when the ECS task launch reports failures."""

    mock_ecs = MockEcsClient(
        fail_times=1, fail_responses=[{"failures": ["task placement failed"]}]
    )

    async def scenario() -> None:
        monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: mock_ecs)
        publisher = Publisher(queue_timeout_seconds=0.25, max_attempts=3)
        await _run_publisher_until(
            publisher, mock_ecs, _publish_request(), expected_calls=2
        )

    asyncio.run(scenario())
    assert len(mock_ecs.run_task_calls) == 2


def test_publisher_gives_up_after_exhausting_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The publish worker stops retrying after max_attempts and gives up."""

    mock_ecs = MockEcsClient(fail_times=99)

    async def scenario() -> None:
        monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: mock_ecs)
        publisher = Publisher(queue_timeout_seconds=0.25, max_attempts=2)
        await _run_publisher_until(
            publisher, mock_ecs, _publish_request(), expected_calls=2
        )

    asyncio.run(scenario())
    assert len(mock_ecs.run_task_calls) == 2
