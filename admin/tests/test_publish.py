"""Unit tests for the publish worker queue."""

import asyncio
import contextlib
import time
from collections.abc import Callable
from uuid import UUID, uuid4

import boto3  # type: ignore[import-untyped]
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import select

from api.database import models as database
from api.settings import settings
from api.utils.prompt import compute_model_prompt_hash
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


def _publish_request(extra_details: str | None = None) -> PublishRequest:
    """Build a publish request for a fresh run."""
    return PublishRequest(
        set_id=uuid4(),
        draft_id=uuid4(),
        run_id=uuid4(),
        extra_details=extra_details,
    )


async def _create_completed_set_and_publish_run(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[database.Set, database.Run]:
    """Create a COMPLETED set and a PENDING publish run for the publisher tests."""
    async with session_factory() as session:
        set_ = database.Set(
            model="black-forest-labs/FLUX.2-klein-4B",
            status=database.SetStatus.COMPLETED,
        )
        session.add(set_)
        await session.flush()
        draft = database.Draft(
            set_id=set_.set_id,
            prompt="a cat",
            model_prompt_hash=compute_model_prompt_hash(set_.model, "a cat"),
            status=database.DraftStatus.COMMITTED,
        )
        session.add(draft)
        await session.flush()
        run = database.Run(
            external_run_id=None,
            set_id=set_.set_id,
            draft_id=draft.draft_id,
            type=database.RunType.PUBLISH,
            status=database.RunStatus.PENDING,
        )
        session.add(run)
        await session.commit()
        await session.refresh(set_)
        await session.refresh(run)
        return set_, run


async def _get_run(
    session_factory: async_sessionmaker[AsyncSession], run_id: UUID
) -> database.Run | None:
    """Get a run by id from the database."""
    async with session_factory() as session:
        return (
            (
                await session.execute(
                    select(database.Run).where(database.Run.run_id == run_id)
                )
            )
            .scalars()
            .first()
        )


def test_publisher_marks_run_failed_and_set_failed_on_permanent_launch_failure(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The publisher marks the run FAILED and the set FAILED when launch attempts exhaust."""

    async def scenario() -> None:
        set_, run = await _create_completed_set_and_publish_run(session_factory)
        monkeypatch.setattr(
            boto3, "client", lambda *args, **kwargs: MockEcsClient(fail_times=1)
        )
        publisher = Publisher(
            queue_timeout_seconds=0.25,
            max_attempts=1,
            session_factory=session_factory,
        )
        task = asyncio.create_task(publisher.run())
        try:
            await publisher.put(
                PublishRequest(
                    set_id=set_.set_id,
                    draft_id=run.draft_id,
                    run_id=run.run_id,
                )
            )
            await _wait_for_condition(
                lambda: run.status == database.RunStatus.FAILED, timeout=5.0
            )
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            await publisher.aclose()

        failed_run = await _get_run(session_factory, run.run_id)
        assert failed_run is not None
        assert failed_run.status == database.RunStatus.FAILED
        assert set_.status == database.SetStatus.FAILED


def test_publisher_submits_ecs_task_and_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The publish worker launches one Fargate task and records the task arn."""

    mock_ecs = MockEcsClient()
    request = _publish_request()

    async def scenario() -> None:
        monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: mock_ecs)
        publisher = Publisher(queue_timeout_seconds=0.25, max_attempts=3)
        await _run_publisher_until(publisher, mock_ecs, request, expected_calls=1)

    asyncio.run(scenario())
    assert len(mock_ecs.run_task_calls) == 1
    kwargs = mock_ecs.run_task_calls[0]
    assert kwargs["cluster"] == settings.publish_ecs_cluster
    assert kwargs["taskDefinition"] == settings.publish_task_family
    assert kwargs["launchType"] == "FARGATE"
    assert kwargs["count"] == 1
    override = kwargs["overrides"]["containerOverrides"][0]
    assert override["name"] == settings.publish_container
    assert override["command"] == [
        "publish",
        "publish",
        "--run-id",
        str(request.run_id),
    ]


def test_publisher_submits_ecs_task_with_extra_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The publish worker forwards optional extra details to the task command."""

    mock_ecs = MockEcsClient()

    async def scenario() -> None:
        monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: mock_ecs)
        publisher = Publisher(queue_timeout_seconds=0.25, max_attempts=3)
        await _run_publisher_until(
            publisher,
            mock_ecs,
            _publish_request(extra_details="a dry lake"),
            expected_calls=1,
        )

    asyncio.run(scenario())
    assert len(mock_ecs.run_task_calls) == 1
    command = mock_ecs.run_task_calls[0]["overrides"]["containerOverrides"][0][
        "command"
    ]
    assert command[0:3] == ["publish", "publish", "--run-id"]
    assert command[4:] == ["--extra-details", "a dry lake"]


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
