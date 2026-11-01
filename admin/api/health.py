"""Health endpoints for the Unending Admin API."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

health_router = APIRouter()


@health_router.get("/health/alive")
async def alive() -> JSONResponse:
    """Liveness probe."""
    return JSONResponse(status_code=200, content={"status": "alive"})


@health_router.get("/health/ready")
async def ready() -> JSONResponse:
    """Readiness probe."""
    return JSONResponse(status_code=200, content={"status": "ready"})
