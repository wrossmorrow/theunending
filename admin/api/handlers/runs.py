"""Run route handlers."""

from uuid import UUID

from fastapi import HTTPException
from fastapi import status as http_status
from sqlmodel import Session

from api import models


def list_runs(
    db: Session,
    status: models.RunStatus | None = None,
    set_id: str | None = None,
    draft_id: str | None = None,
) -> models.RunsResponse:
    """List runs with query filters."""
    raise HTTPException(
        status_code=http_status.HTTP_501_NOT_IMPLEMENTED,
        detail="Run listing is not implemented yet.",
    )


def get_run(run_id: UUID, db: Session) -> models.Run:
    """Get a specific run by id alone (or 404)."""
    raise HTTPException(
        status_code=http_status.HTTP_501_NOT_IMPLEMENTED,
        detail="Run retrieval is not implemented yet.",
    )


def redo_run(run_id: UUID, db: Session) -> models.Run:
    """Redo a run (requires FAILED status; creates a distinct run)."""
    raise HTTPException(
        status_code=http_status.HTTP_501_NOT_IMPLEMENTED,
        detail="Run redo is not implemented yet.",
    )


def update_run_status(
    run_id: UUID, update: models.RunStatusUpdate, db: Session
) -> models.Run:
    """Update a run status (system call)."""
    raise HTTPException(
        status_code=http_status.HTTP_501_NOT_IMPLEMENTED,
        detail="Run status update is not implemented yet.",
    )
