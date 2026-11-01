"""Run API routes for the Unending Admin API."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.database import models as database
from api.database.db import get_session_factory
from api.utils.jobs import ExternalJobClient, get_job_client
from api.v0.handlers import runs as runs_handlers
from api.v0.schema import models

runs_router = APIRouter()


@runs_router.get(
    "/runs", response_model=models.RunsResponse, status_code=status.HTTP_200_OK
)
async def list_runs(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
    status: database.RunStatus | None = None,
    set_id: str | None = None,
    draft_id: str | None = None,
) -> models.RunsResponse:
    """List runs with query filters."""
    return await runs_handlers.list_runs(
        session_factory, status=status, set_id=set_id, draft_id=draft_id
    )


@runs_router.get(
    "/runs/{run_id}", response_model=database.Run, status_code=status.HTTP_200_OK
)
async def get_run(
    run_id: UUID,
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> database.Run:
    """Get a specific run by id alone (or 404)."""
    return await runs_handlers.get_run(run_id, session_factory)


@runs_router.post(
    "/runs/{run_id}",
    response_model=database.Run,
    status_code=status.HTTP_201_CREATED,
)
async def redo_run(
    run_id: UUID,
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
    job_client: Annotated[ExternalJobClient, Depends(get_job_client)],
) -> database.Run:
    """Redo a run (requires FAILED status; creates a distinct run)."""
    return await runs_handlers.redo_run(run_id, session_factory, job_client)


@runs_router.put(
    "/runs/{run_id}/status",
    response_model=database.Run,
    status_code=status.HTTP_200_OK,
)
async def update_run_status(
    run_id: UUID,
    update: models.RunStatusUpdate,
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> database.Run:
    """Update a run status (system call)."""
    return await runs_handlers.update_run_status(run_id, update, session_factory)
