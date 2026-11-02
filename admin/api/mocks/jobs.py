"""Mock external job system for local runs and integration tests."""

from uuid import uuid4

from fastapi import FastAPI, status
from pydantic import BaseModel

from api.database.models import RunType


class JobCreate(BaseModel):
    """Job creation request accepted from the admin API."""

    job_type: RunType
    set_id: str | None = None
    draft_id: str | None = None
    model_prompt_hash: str | None = None


class JobCreated(BaseModel):
    """Job creation response returned by the external job system."""

    external_run_id: str


api = FastAPI(title="Unending Mock Job System")


@api.get("/health/alive")
async def alive() -> dict[str, str]:
    """Liveness probe for the mock external job system."""
    return {"status": "alive"}


@api.get("/health/ready")
async def ready() -> dict[str, str]:
    """Readiness probe for the mock external job system."""
    return {"status": "ready"}


@api.post("/jobs", response_model=JobCreated, status_code=status.HTTP_201_CREATED)
async def create_job(body: JobCreate) -> JobCreated:
    """Create a mock external job and return a mock external run id."""
    return JobCreated(external_run_id=str(uuid4()))
