"""External job system client for the Unending Admin API."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import httpx
from fastapi import Request
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.database import models as database
from api.database.models import DraftStatus, RunStatus, RunType, SetStatus
from api.settings import settings


class JobParameters(BaseModel):
    """Parameters for an external job creation request."""

    model_id: str
    s3_bucket: str
    s3_prefix: str
    prompt: str
    status_update_url: str
    status_update_admin_run_id: UUID


class JobRequest(BaseModel):
    """A job request to enqueue for an external job system submission."""

    run_id: UUID
    job_type: RunType
    job_params: JobParameters
    attempts: int = 0


class JobAPIResponse(BaseModel):
    """Response from the external job system on a successful submission."""

    external_run_id: str


class ExternalJobClient:
    """Client for triggering external jobs through the job system."""

    def __init__(
        self,
        base_url: str,
        session_factory: async_sessionmaker[AsyncSession],
        queue_timeout_seconds: float = 30.0,
        submit_timeout_seconds: float = 60.0,
        max_attempts: int = 3,
    ) -> None:
        """Create a client with the given base URL and timeout."""
        headers = (
            {"Authorization": f"Bearer {settings.job_bearer_token}"}
            if (settings.job_bearer_token)
            else None
        )
        self._client = httpx.AsyncClient(
            base_url=base_url, timeout=submit_timeout_seconds, headers=headers
        )
        self._queue: asyncio.Queue[JobRequest] = asyncio.Queue()
        self._qtimeout_seconds = queue_timeout_seconds
        self._session_factory = session_factory
        self._max_attempts = max_attempts

        self._worker_task: asyncio.Task | None = None

        self._closed = False

    async def aclose(self) -> None:
        """Close the underlying HTTP client and stop the worker."""
        if self._worker_task is not None:
            await self.cancel()
        await self._client.aclose()

    async def cancel(self) -> None:
        """Cancel the worker task, joining any pending queue items first."""
        await self.join()
        if self._worker_task is not None and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                print(
                    "Acknowledged external jobs worker has been joined and successfully cancelled."
                )

    async def start(self) -> None:
        """Start the worker task; hold a reference to avoid strangeness."""
        if self._worker_task is not None and not self._worker_task.done():
            return
        self._worker_task = asyncio.create_task(self.run())

    async def run(self) -> None:
        """Processes items pulled from the queue."""
        while True:
            try:
                request = await asyncio.wait_for(
                    self._queue.get(), timeout=self._qtimeout_seconds
                )
            except TimeoutError:
                # Timed out waiting for a queued job; try again.
                continue

            response: JobAPIResponse | None = None
            try:
                response = await self.submit_job(request)
                self._queue.task_done()
                await self.update_job(request, response, RunStatus.SUBMITTED)
            except Exception as e:  # noqa: BLE001
                self._queue.task_done()
                request.attempts += 1
                if request.attempts < self._max_attempts:
                    await self._queue.put(request)
                else:
                    print(
                        "Permanently failed to submit enqueued job run for "
                        f"{request.run_id} {e.__class__.__name__} {e}"
                    )
                    await self.update_job(request, None, RunStatus.FAILED)

    async def join(self) -> None:
        """Process and clear pending queue items (used during shutdown)."""
        self._closed = True
        while True:
            try:
                request = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            response: JobAPIResponse | None = None
            try:
                response = await self.submit_job(request)
                self._queue.task_done()
                await self.update_job(request, response, RunStatus.SUBMITTED)
            except Exception as e:  # noqa: BLE001
                self._queue.task_done()
                print(
                    "Permanently failed to submit enqueued job run for "
                    f"{request.run_id} {e.__class__.__name__} {e}"
                )
                await self.update_job(request, None, RunStatus.FAILED)

    async def request_job(self, job_request: JobRequest) -> None:
        """Enqueue a job (type and params) if not closed."""
        if self._closed:
            raise ValueError("Queue is closed (shutdown), cannot enqueue more requests")
        await self._queue.put(job_request)

    async def submit_job(self, job_request: JobRequest) -> JobAPIResponse:
        """Create an external job of the given type and return the external run id."""
        path = "/evaluate" if job_request.job_type == RunType.EVALUATION else "/batch"
        try:
            response = await self._client.post(
                path, json=job_request.job_params.model_dump(mode="json")
            )
            response.raise_for_status()
            return JobAPIResponse.model_validate(response.json())
        except httpx.HTTPStatusError as e:
            print(f"Failed job call: {e.response.status_code} {e.response.text}")
            raise
        except ValidationError as e:
            print(f"Job response validation failed: {e}")
            raise

    async def update_job(
        self,
        request: JobRequest,
        response: JobAPIResponse | None,
        status: RunStatus,
    ) -> None:
        """Record a worker-driven run status update for an enqueued job."""
        async with self._session_factory() as session:
            runs_table = database.Run.metadata.tables[database.Run.__tablename__]
            run = (
                (
                    await session.execute(
                        select(database.Run)
                        .where(runs_table.c.run_id == request.run_id)
                        .with_for_update()
                    )
                )
                .scalars()
                .first()
            )
            if run is None:
                return
            run.status = status
            if response is not None:
                run.external_run_id = response.external_run_id
                run.submitted_at = datetime.now(UTC)
            run.updated_at = datetime.now(UTC)
            if status in (RunStatus.COMPLETED, RunStatus.FAILED):
                run.finished_at = datetime.now(UTC)
            session.add(run)
            if status in (RunStatus.COMPLETED, RunStatus.FAILED):
                # Worker-driven terminal status updates follow the same draft/set
                # propagation rules as status updates from the external job system.
                if run.type == database.RunType.BATCH:
                    committed_set = await session.get(database.Set, run.set_id)
                    if committed_set is not None:
                        committed_set.status = (
                            SetStatus.COMPLETED
                            if status == database.RunStatus.COMPLETED
                            else SetStatus.FAILED
                        )
                        session.add(committed_set)
                elif run.type == database.RunType.EVALUATION:
                    draft = await session.get(database.Draft, run.draft_id)
                    if draft is not None:
                        draft.status = DraftStatus(status.value)
                        session.add(draft)
            await session.commit()


def get_job_client(request: Request) -> ExternalJobClient:
    """Return the shared external job system client from app state."""
    return request.app.state.job_client
