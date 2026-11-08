"""Unit tests for the external job system worker queue."""

import asyncio
import contextlib
import json
import time
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.database import models as database
from api.settings import settings
from api.utils.jobs import (
    ExternalJobClient,
    JobAPIResponse,
    JobParameters,
    JobRequest,
)
from api.utils.prompt import compute_model_prompt_hash


class MockSubmitJobClient(ExternalJobClient):
    """Mock external job system client that controls submission outcomes."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        fail_times: int = 0,
        max_attempts: int = 3,
    ) -> None:
        """Create a mock client that fails submission attempts on purpose."""
        super().__init__(
            base_url=settings.job_base_url,
            session_factory=session_factory,
            queue_timeout_seconds=0.25,
            submit_timeout_seconds=5.0,
            max_attempts=max_attempts,
        )
        self.submitted_requests: list[JobRequest] = []
        self.fail_times = fail_times
        self.failures_remaining = fail_times

    async def submit_job(self, job_request: JobRequest) -> JobAPIResponse:
        """Record the submission, optionally failing it like the job system."""
        self.submitted_requests.append(job_request)
        if self.failures_remaining > 0:
            self.failures_remaining -= 1
            raise httpx.ConnectError("mock external job submission failure")
        return JobAPIResponse(external_run_id=f"external-{job_request.run_id}")


async def _create_run(
    session_factory: async_sessionmaker[AsyncSession],
) -> database.Run:
    """Create a set, draft, and pending run and return the run."""
    async with session_factory() as session:
        set_ = database.Set(
            model="black-forest-labs/FLUX.2-klein-4B", status=database.SetStatus.DRAFT
        )
        session.add(set_)
        await session.flush()
        draft_prompt = f"a cat {uuid4().hex}"
        draft = database.Draft(
            set_id=set_.set_id,
            prompt=draft_prompt,
            model_prompt_hash=compute_model_prompt_hash(set_.model, draft_prompt),
            status=database.DraftStatus.COMPLETED,
        )
        session.add(draft)
        await session.flush()
        run = database.Run(
            external_run_id=None,
            set_id=set_.set_id,
            draft_id=draft.draft_id,
            type=database.RunType.EVALUATION,
            status=database.RunStatus.PENDING,
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        return run


async def _get_run(
    session_factory: async_sessionmaker[AsyncSession], run_id: UUID
) -> database.Run | None:
    async with session_factory() as session:
        return (
            (
                await session.execute(
                    select(database.Run).where(
                        database.Run.metadata.tables[
                            database.Run.__tablename__
                        ].c.run_id
                        == run_id
                    )
                )
            )
            .scalars()
            .first()
        )


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


async def _wait_for_run_status(
    session_factory: async_sessionmaker[AsyncSession],
    run_id: UUID,
    status: database.RunStatus,
    timeout: float = 5.0,
) -> database.Run:
    """Poll the database until the run reaches the given status."""
    deadline = time.monotonic() + timeout
    while True:
        run = await _get_run(session_factory, run_id)
        if run is not None and run.status == status:
            return run
        if time.monotonic() > deadline:
            raise AssertionError(
                f"Timed out waiting for run status {status}; last status {run.status if run else None}"
            )
        await asyncio.sleep(0.01)


def _job_request(run_id: UUID) -> JobRequest:
    """Build an evaluation job request for the given run."""
    return JobRequest(
        run_id=run_id,
        job_type=database.RunType.EVALUATION,
        job_params=JobParameters(
            model_id="black-forest-labs/FLUX.2-klein-4B",
            s3_bucket="unending-local",
            s3_prefix="drafts/some-hash",
            prompt="a cat",
            status_update_url=f"http://localhost:8000/api/v0/runs/{run_id}/status",
            status_update_admin_run_id=run_id,
        ),
    )


def test_worker_submits_enqueued_job_and_marks_run_submitted(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A worker submission marks the run SUBMITTED with the external run id."""

    async def scenario() -> None:
        run = await _create_run(session_factory)
        client = MockSubmitJobClient(session_factory=session_factory)
        task = asyncio.create_task(client.run())
        try:
            await client.request_job(_job_request(run.run_id))
            submitted = await _wait_for_run_status(
                session_factory, run.run_id, database.RunStatus.SUBMITTED
            )
            assert submitted.external_run_id is not None
            assert submitted.external_run_id.startswith("external-")
            assert submitted.submitted_at is not None
            assert submitted.finished_at is None

            events = await _get_status_events(session_factory, run.run_id)
            assert len(events) == 1
            assert events[0].status == database.RunStatus.SUBMITTED
            assert events[0].source == database.RunStatusEventSource.INTERNAL
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    asyncio.run(scenario())


def test_worker_retries_failed_submissions_then_succeeds(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A worker retries failed submissions and marks the run SUBMITTED on success."""

    async def scenario() -> None:
        run = await _create_run(session_factory)
        client = MockSubmitJobClient(
            session_factory=session_factory, fail_times=2, max_attempts=3
        )
        task = asyncio.create_task(client.run())
        try:
            await client.request_job(_job_request(run.run_id))
            submitted = await _wait_for_run_status(
                session_factory, run.run_id, database.RunStatus.SUBMITTED
            )
            assert len(client.submitted_requests) == 3
            assert submitted.external_run_id is not None
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    asyncio.run(scenario())


def test_worker_marks_run_failed_after_exhausting_submission_attempts(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A worker gives up after max attempts and marks the run FAILED."""

    async def scenario() -> None:
        run = await _create_run(session_factory)
        client = MockSubmitJobClient(
            session_factory=session_factory, fail_times=99, max_attempts=2
        )
        task = asyncio.create_task(client.run())
        try:
            await client.request_job(_job_request(run.run_id))
            failed = await _wait_for_run_status(
                session_factory, run.run_id, database.RunStatus.FAILED
            )
            assert len(client.submitted_requests) == 2
            assert failed.finished_at is not None
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    asyncio.run(scenario())


def test_cancel_job_posts_to_cancel_path(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The job client posts a cancel to the cancel path with the external run id."""

    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"status": "CANCELLED"})

    real_async_client = httpx.AsyncClient

    def mock_async_client(**kwargs: Any) -> httpx.AsyncClient:
        return real_async_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", mock_async_client)

    async def scenario() -> None:
        client = ExternalJobClient(
            base_url="http://mock-jobs", session_factory=session_factory
        )
        await client.cancel_job("external-run-123")
        await client.aclose()

    asyncio.run(scenario())

    assert len(captured) == 1
    assert captured[0].url.path == "/cancel"
    assert json.loads(captured[0].content) == {"external_run_id": "external-run-123"}
