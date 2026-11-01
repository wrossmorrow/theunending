"""Set route handlers."""

from uuid import UUID

from sqlmodel import Session

from api import models


def list_sets(  # type: ignore[empty-body]
    db: Session,
    status: models.SetStatus | None = None,
    post_date: str | None = None,
    slug: str | None = None,
    name: str | None = None,
) -> models.SetsResponse:
    """List sets with query filters."""


def create_set(  # type: ignore[empty-body]
    db: Session, body: models.SetCreate
) -> models.Set:
    """Create a set (DRAFT status); requires model, optional slug/name."""


def get_set(  # type: ignore[empty-body]
    set_id: UUID, db: Session
) -> models.Set:
    """Get one set (or 404)."""


def patch_set(  # type: ignore[empty-body]
    set_id: UUID, update: models.Set, db: Session
) -> models.Set:
    """Update set fields (only slug/name; DRAFT only)."""


def delete_set(  # type: ignore[empty-body]
    set_id: UUID, db: Session
) -> models.Set:
    """Mark set ABANDONED (soft; DRAFT only)."""
