import asyncio
from uuid import UUID

import boto3  # type: ignore[import-untyped]
from fastapi import Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.database import models as database
from api.settings import settings
from api.utils.jobs import finalize_run_status


class PublishLaunchFailed(Exception): ...


class PublishRequest(BaseModel):
    set_id: UUID
    draft_id: UUID
    run_id: UUID
    attempts: int = 0


class Publisher:
    def __init__(
        self,
        queue_timeout_seconds: float = 30.0,
        max_attempts: int = 3,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._ecs = boto3.client("ecs", region_name=settings.aws_region_name)
        self._queue: asyncio.Queue[PublishRequest] = asyncio.Queue()
        self._qtimeout_seconds = queue_timeout_seconds
        self._max_attempts = max_attempts
        self._session_factory = session_factory
        self._worker_task: asyncio.Task | None = None
        self._closed = False

    async def put(self, request: PublishRequest) -> None:
        if self._closed:
            raise ValueError("Queue is closed (shutdown), cannot enqueue more requests")
        await self._queue.put(request)

    async def aclose(self) -> None:
        if self._worker_task is not None:
            await self.cancel()

    async def cancel(self) -> None:
        """Cancel the worker task, joining any pending queue items first."""
        await self.join()
        if self._worker_task is not None and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                print(
                    "Acknowledged publisher worker has been joined and successfully cancelled."
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

            response: str | Exception
            try:
                response = await asyncio.to_thread(self.publish, request)
            except Exception as e:  # noqa: BLE001
                response = e
            finally:
                self._queue.task_done()

            if isinstance(response, Exception):
                request.attempts += 1
                if request.attempts < self._max_attempts:
                    await self._queue.put(request)
                else:
                    if self._session_factory is not None:
                        await finalize_run_status(
                            session_factory=self._session_factory,
                            run_id=request.run_id,
                            status=database.RunStatus.FAILED,
                        )
                    print(
                        "Permanently failed to submit enqueued publish run for "
                        f"{request.run_id} {response.__class__.__name__} {response}"
                    )

    async def join(self) -> None:
        """Process and clear pending queue items (used during shutdown)."""
        self._closed = True
        while True:
            try:
                request = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                return

            response: str | Exception
            try:
                response = await asyncio.to_thread(self.publish, request)
            except Exception as e:  # noqa: BLE001
                response = e
            finally:
                self._queue.task_done()

            if isinstance(response, Exception):
                print(
                    "Permanently failed to submit enqueued publish run for "
                    f"{request.run_id} {response.__class__.__name__} {response}"
                )

    def publish(self, request: PublishRequest) -> str:
        response = self._ecs.run_task(
            cluster=settings.publish_ecs_cluster,
            taskDefinition=settings.publish_task_family,
            launchType="FARGATE",
            count=1,
            networkConfiguration={
                "awsvpcConfiguration": {
                    "subnets": settings.publish_private_subnet_ids,
                    "securityGroups": [
                        settings.publish_security_group_id,
                    ],
                    "assignPublicIp": "DISABLED",
                }
            },
            overrides={
                "containerOverrides": [
                    {
                        "name": settings.publish_container,
                        "command": [
                            "publish", # module
                            "publish", # command
                            "--run-id",
                            str(request.run_id),
                        ],
                    }
                ]
            },
            startedBy=f"{request.set_id}-{request.run_id}"[:128],
            clientToken=str(request.run_id),
        )

        # e.g. capacity or config problems: the launch failed, retry from the outbox
        failures = response.get("failures")
        if failures:
            raise PublishLaunchFailed(f"Publish start failure(s): {failures}")

        tasks = response.get("tasks") or []
        if not tasks:
            raise PublishLaunchFailed("Publish start response contained no tasks.")

        return tasks[0]["taskArn"]


def get_publisher(request: Request) -> Publisher:
    """Return the publisher from app state."""
    return request.app.state.publisher
