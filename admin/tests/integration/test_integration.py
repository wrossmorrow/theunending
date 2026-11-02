"""Integration tests for the Unending Admin API against a live server."""

import os
from typing import Any

import httpx
import pytest


@pytest.fixture
def http_client() -> httpx.Client:
    """HTTP client bound to the admin API base URL from the environment."""
    base_url = os.environ.get("ADMIN_API_BASE_URL", "http://localhost:8000")
    return httpx.Client(base_url=base_url, timeout=10.0)


def test_health_alive(http_client: httpx.Client) -> None:
    """Liveness probe returns 200 with an alive status."""
    response = http_client.get("/health/alive")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_health_ready(http_client: httpx.Client) -> None:
    """Readiness probe returns 200 with a ready status."""
    response = http_client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_list_sets(http_client: httpx.Client) -> None:
    """List sets returns a 200 with a sets collection."""
    response = http_client.get("/api/v0/sets")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    assert "sets" in body
