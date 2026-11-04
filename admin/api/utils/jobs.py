"""External job system client for the Unending Admin API."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import httpx
from fastapi import Request
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.database import models as database
from api.database.models import RunStatus, RunType
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
    """A job request."""

    run_id: UUID
    job_type: RunType
    job_params: JobParameters
    attempts: int = 0


class JobAPIResponse(BaseModel):
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
        """Close the underlying HTTP client."""
        if self._worker_task is not None:
            await self.cancel()
        await self._client.aclose()

    async def cancel(self) -> None:
        """Cancel the task if defined."""
        await self.join()
        if self._worker_task is not None:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                print(
                    "Acknowledged external jobs worker has been joined and successfully cancelled."
                )

    async def start(self) -> None:
        """Start the worker task; hold a reference to avoid strangeness."""
        self._worker_task = asyncio.create_task(self.run())

    async def run(self) -> None:
        """Processes items pulled from the queue."""
        while True:
            response: JobAPIResponse | None = None
            try:
                request = await asyncio.wait_for(
                    self._queue.get(), timeout=self._qtimeout_seconds
                )
                response = await self.submit_job(request)
                self._queue.task_done()
            except TimeoutError:
                pass
            except Exception as e:  # noqa: BLE001
                print(f"Failed to submit enqueued job run for {request.run_id}")
                self._queue.task_done()
                request.attempts += 1
                if request.attempts < self._max_attempts:
                    await self._queue.put(request)
                else:
                    print(
                        "Permanently failed to submit enqueued job run for "
                        f"{request.run_id} {e.__class__.__name__} {e}"
                    )
                    await self.update_job(request, response, RunStatus.FAILED)
            else:
                # This is here to avoid catching errors from this and resubmitting a job
                await self.update_job(request, response, RunStatus.SUBMITTED)

    async def join(self) -> None:
        """Processes items pulled from the queue."""
        self._closed = True
        while True:
            try:
                request = self._queue.get_nowait()
                response = await self.submit_job(request)
                self._queue.task_done()
            except asyncio.QueueEmpty:
                return
            except Exception as e:  # noqa: BLE001
                self._queue.task_done()
                print(
                    "Permanently failed to submit enqueued job run for "
                    f"{request.run_id} {e.__class__.__name__} {e}"
                )
                await self.update_job(request, None, RunStatus.FAILED)
            else:
                # This is here to avoid catching errors from this and resubmitting
                await self.update_job(request, response, RunStatus.SUBMITTED)

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
        async with self._session_factory() as session:
            run = await session.get(database.Run, request.run_id)  # with for update
            if run is None:
                return
            run.status = status
            if response is not None:
                run.external_job_id = response.external_run_id
                run.submitted = datetime.now(UTC)
            run.updated_at = datetime.now(UTC)
            session.add(run)
            await session.commit()


def get_job_client(request: Request) -> ExternalJobClient:
    """Return the shared external job system client from app state."""
    return request.app.state.job_client
