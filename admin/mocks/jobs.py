"""Mock external job system for local runs and integration tests."""

import asyncio
import uuid
from typing import Any

import httpx
from fastapi import FastAPI, status
from pydantic import BaseModel


class JobCreate(BaseModel):
    """Job creation request accepted from the admin API."""

    s3_bucket: str
    s3_prefix: str
    prompt: str
    status_update_url: str
    status_update_admin_run_id: uuid.UUID


class JobCreated(BaseModel):
    """Job creation response returned to the admin API."""

    external_run_id: str


class CancelRequest(BaseModel):
    """Job cancellation request accepted from the admin API."""

    external_run_id: str
    job_type: str


api = FastAPI(title="Unending Mock Job System")

STATUS_UPDATE_DELAY_SECONDS = 2.0
CANCELLED_EXTERNAL_RUN_IDS: set[str] = set()


async def _send_status_update(
    status_update_url: str, status: str, message: str, details: dict[str, Any]
) -> None:
    """Send a run status update to the admin API."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.put(
            status_update_url,
            json={"status": status, "message": message, "details": details},
        )
        response.raise_for_status()


async def _run_job(
    status_update_url: str,
    external_run_id: str,
    status_update_admin_run_id: uuid.UUID,
) -> None:
    """Simulate a job: IN_PROGRESS then COMPLETED via status updates."""
    if external_run_id in CANCELLED_EXTERNAL_RUN_IDS:
        return
    await asyncio.sleep(STATUS_UPDATE_DELAY_SECONDS)
    await _send_status_update(
        status_update_url,
        "IN_PROGRESS",
        "external job started",
        {"phase": "IN_PROGRESS"},
    )
    await asyncio.sleep(STATUS_UPDATE_DELAY_SECONDS)
    await _send_status_update(
        status_update_url,
        "COMPLETED",
        "external job completed",
        {"phase": "COMPLETED"},
    )


@api.get("/health/alive")
async def alive() -> dict[str, str]:
    """Liveness probe for the mock external job system."""
    return {"status": "alive"}


@api.get("/health/ready")
async def ready() -> dict[str, str]:
    """Readiness probe for the mock external job system."""
    return {"status": "ready"}


@api.post("/evaluate", response_model=JobCreated, status_code=status.HTTP_201_CREATED)
async def create_evaluate_job(body: JobCreate) -> JobCreated:
    """Create a mock evaluate job and return a mock external run id."""
    external_run_id = str(uuid.uuid4())

    async def _background() -> None:
        await _run_job(
            body.status_update_url, external_run_id, body.status_update_admin_run_id
        )

    asyncio.create_task(_background())
    return JobCreated(external_run_id=external_run_id)


@api.post("/batch", response_model=JobCreated, status_code=status.HTTP_201_CREATED)
async def create_batch_job(body: JobCreate) -> JobCreated:
    """Create a mock batch job and return a mock external run id."""
    external_run_id = str(uuid.uuid4())

    async def _background() -> None:
        await _run_job(
            body.status_update_url, external_run_id, body.status_update_admin_run_id
        )

    asyncio.create_task(_background())
    return JobCreated(external_run_id=external_run_id)


@api.post("/cancel", status_code=status.HTTP_200_OK)
async def cancel_job(body: CancelRequest) -> dict[str, str]:
    """Mark an external run as cancelled in the mock job system."""
    CANCELLED_EXTERNAL_RUN_IDS.add(body.external_run_id)
    return {"status": "CANCELLED", "job_type": body.job_type}
