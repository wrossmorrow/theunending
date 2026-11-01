"""External job system client for the Unending Admin API."""

import httpx


class ExternalJobClient:
    """Client for triggering external jobs through the job system."""

    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        """Create a client with the given base URL and timeout."""
        self._client = httpx.Client(base_url=base_url, timeout=timeout)

    def create_job(self, payload: dict) -> str:
        """Create an external job and return the external run id."""
        response = self._client.post("/jobs", json=payload)
        response.raise_for_status()
        return str(response.json()["external_run_id"])
