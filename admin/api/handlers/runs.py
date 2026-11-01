"""Run route handlers."""

from uuid import UUID

from sqlmodel import Session

from api import models


def list_runs(  # type: ignore[empty-body]
    db: Session,
    status: models.RunStatus | None = None,
    set_id: str | None = None,
    draft_id: str | None = None,
) -> models.RunsResponse:
    """List runs with query filters."""


def get_run(  # type: ignore[empty-body]
    run_id: UUID, db: Session
) -> models.Run:
    """Get a specific run by id alone (or 404)."""


def redo_run(  # type: ignore[empty-body]
    run_id: UUID, db: Session
) -> models.Run:
    """Redo a run (requires FAILED status; creates a distinct run)."""


def update_run_status(  # type: ignore[empty-body]
    run_id: UUID, update: models.RunStatusUpdate, db: Session
) -> models.Run:
    """Update a run status (system call)."""
