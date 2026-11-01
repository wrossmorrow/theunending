"""External job system client for the Unending Admin API."""

import httpx

from api.settings import Settings


class ExternalJobClient:
    """Client for triggering external jobs through the job system."""

    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        """Create a client with the given base URL and timeout."""
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout)

    async def create_job(self, payload: dict) -> str:
        """Create an external job and return the external run id."""
        response = await self._client.post("/jobs", json=payload)
        response.raise_for_status()
        return str(response.json()["external_run_id"])


def get_job_client() -> ExternalJobClient:
    """Return the external job system client."""
    return ExternalJobClient(base_url=Settings().job_base_url)
