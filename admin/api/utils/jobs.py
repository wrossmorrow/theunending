"""External job system client for the Unending Admin API."""

import httpx
from fastapi import Request
from pydantic import BaseModel, ValidationError

from api.database.models import RunType
from api.settings import settings


class JobParameters(BaseModel):
    """Parameters for an external job creation request."""

    s3_bucket: str
    s3_prefix: str
    prompt: str
    status_update_url: str
    status_update_admin_run_id: str


class JobAPIResponse(BaseModel):
    external_run_id: str


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

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def create_job(self, job_type: RunType, job_request: JobParameters) -> str:
        """Create an external job of the given type and return the external run id."""
        path = "/evaluate" if job_type == RunType.EVALUATION else "/batch"
        try:
            response = await self._client.post(
                path, json=job_request.model_dump(mode="json")
            )
            response.raise_for_status()
            data = JobAPIResponse.model_validate(response.json())
            return data.external_run_id
        except httpx.HTTPStatusError as e:
            print(f"Failed job call: {e.response.status_code} {e.response.text}")
            raise
        except ValidationError as e:
            print(f"Job response validation failed: {e}")
            raise


def get_job_client(request: Request) -> ExternalJobClient:
    """Return the shared external job system client from app state."""
    return request.app.state.job_client
