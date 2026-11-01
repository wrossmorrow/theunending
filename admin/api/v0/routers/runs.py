"""Run API routes for the Unending Admin API."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from api.database import models as database
from api.v0.handlers import runs as runs_handlers
from api.v0.handlers.db import get_db
from api.v0.schema import models

runs_router = APIRouter()


@runs_router.get(
    "/runs", response_model=models.RunsResponse, status_code=status.HTTP_200_OK
)
async def list_runs(
    db: Annotated[Session, Depends(get_db)],
    status: database.RunStatus | None = None,
    set_id: str | None = None,
    draft_id: str | None = None,
) -> models.RunsResponse:
    """List runs with query filters."""
    return await runs_handlers.list_runs(
        status=status, set_id=set_id, draft_id=draft_id, db=db
    )


@runs_router.get(
    "/runs/{run_id}", response_model=database.Run, status_code=status.HTTP_200_OK
)
async def get_run(
    run_id: UUID, db: Annotated[Session, Depends(get_db)]
) -> database.Run:
    """Get a specific run by id alone (or 404)."""
    return await runs_handlers.get_run(run_id=run_id, db=db)


@runs_router.post(
    "/runs/{run_id}",
    response_model=database.Run,
    status_code=status.HTTP_201_CREATED,
)
async def redo_run(
    run_id: UUID, db: Annotated[Session, Depends(get_db)]
) -> database.Run:
    """Redo a run (requires FAILED status; creates a distinct run)."""
    return await runs_handlers.redo_run(run_id=run_id, db=db)


@runs_router.put(
    "/runs/{run_id}/status",
    response_model=database.Run,
    status_code=status.HTTP_200_OK,
)
async def update_run_status(
    run_id: UUID,
    update: models.RunStatusUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> database.Run:
    """Update a run status (system call)."""
    return await runs_handlers.update_run_status(run_id=run_id, update=update, db=db)
