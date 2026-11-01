"""Run route handlers."""

from datetime import UTC, datetime
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


def _run_transition_valid(
    current: database.RunStatus, next_status: database.RunStatus
) -> bool:
    """Return whether the run status transition is valid."""
    if current == next_status:
        # Same-state transitions are treated as no-op successes.
        return True
    if current == database.RunStatus.PENDING:
        # PENDING -> IN_PROGRESS (job started) or PENDING -> FAILED (job failed to start).
        return next_status in (
            database.RunStatus.IN_PROGRESS,
            database.RunStatus.FAILED,
        )
    if current == database.RunStatus.IN_PROGRESS:
        # IN_PROGRESS -> COMPLETED (job finished ok) or IN_PROGRESS -> FAILED (job failed).
        return next_status in (
            database.RunStatus.COMPLETED,
            database.RunStatus.FAILED,
        )
    return False


async def update_run_status(
    run_id: UUID,
    update: models.RunStatusUpdate,
    session_factory: sessionmaker[Session],
) -> database.Run:
    """Update a run status (system call)."""
    with session_factory() as session:
        run = session.get(database.Run, run_id)
        if run is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Run {run_id} not found.",
            )
        if not _run_transition_valid(run.status, update.status):
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Invalid run status transition from {run.status} to {update.status}."
                ),
            )

        run.status = update.status
        run.updated_at = datetime.now(UTC)
        if update.status in (
            database.RunStatus.COMPLETED,
            database.RunStatus.FAILED,
        ):
            run.finished_at = datetime.now(UTC)
        session.add(run)
        session.commit()
        session.refresh(run)

        draft = session.get(database.Draft, run.draft_id)
        if draft is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Draft {run.draft_id} not found.",
            )
        draft.status = database.DraftStatus(update.status.value)
        draft.updated_at = datetime.now(UTC)
        session.add(draft)
        session.commit()
        session.refresh(draft)

    return run
