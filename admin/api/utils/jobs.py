"""External job system client for the Unending Admin API."""

import httpx
from pydantic import BaseModel

from api.database.models import RunType
from api.settings import settings


class JobParameters(BaseModel):
    """Parameters for an external job creation request."""

    s3_bucket: str
    s3_prefix: str
    prompt: str
    status_update_url: str
    status_update_admin_run_id: str


class ExternalJobClient:
    """Client for triggering external jobs through the job system."""

    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        """Create a client with the given base URL and timeout."""
        headers = (
            {"Authorization": f"Bearer {settings.job_bearer_token}"}
            if (settings.job_bearer_token)
            else None
        )
        self._client = httpx.AsyncClient(
            base_url=base_url, timeout=timeout, headers=headers
        )

    async def create_job(self, job_type: RunType, job_request: JobParameters) -> str:
        """Create an external job of the given type and return the external run id."""
        path = "/evaluate" if job_type == RunType.EVALUATION else "/batch"
        response = await self._client.post(
            path, json=job_request.model_dump(mode="json")
        )
        response.raise_for_status()
        return str(response.json()["external_run_id"])


def get_job_client() -> ExternalJobClient:
    """Return the external job system client."""
    return ExternalJobClient(base_url=settings.job_base_url)
