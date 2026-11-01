"""Run route handlers."""

from uuid import UUID

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session

from api.database import models as database
from api.v0.schema import models


async def list_runs(
    session_factory: sessionmaker[Session],
    status: database.RunStatus | None = None,
    set_id: str | None = None,
    draft_id: str | None = None,
) -> models.RunsResponse:
    """List runs with query filters."""
    raise HTTPException(
        status_code=http_status.HTTP_501_NOT_IMPLEMENTED,
        detail="Run listing is not implemented yet.",
    )


async def get_run(run_id: UUID, session_factory: sessionmaker[Session]) -> database.Run:
    """Get a specific run by id alone (or 404)."""
    raise HTTPException(
        status_code=http_status.HTTP_501_NOT_IMPLEMENTED,
        detail="Run retrieval is not implemented yet.",
    )


async def redo_run(
    run_id: UUID, session_factory: sessionmaker[Session]
) -> database.Run:
    """Redo a run (requires FAILED status; creates a distinct run)."""
    raise HTTPException(
        status_code=http_status.HTTP_501_NOT_IMPLEMENTED,
        detail="Run redo is not implemented yet.",
    )


async def update_run_status(
    run_id: UUID,
    update: models.RunStatusUpdate,
    session_factory: sessionmaker[Session],
) -> database.Run:
    """Update a run status (system call)."""
    raise HTTPException(
        status_code=http_status.HTTP_501_NOT_IMPLEMENTED,
        detail="Run status update is not implemented yet.",
    )
