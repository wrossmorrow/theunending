"""Draft route handlers."""

from uuid import UUID

from sqlmodel import Session

from api import models


def create_draft(  # type: ignore[empty-body]
    set_id: UUID, body: models.DraftCreate, db: Session
) -> models.Draft:
    """Create a set draft; set must exist and be DRAFT; prompt required."""


def list_drafts(  # type: ignore[empty-body]
    set_id: UUID, db: Session
) -> models.DraftsResponse:
    """List set drafts (created_at desc)."""


def get_draft(  # type: ignore[empty-body]
    set_id: UUID, draft_id: UUID, db: Session
) -> models.Draft:
    """Get a specific set draft (or 404)."""


def commit_draft(  # type: ignore[empty-body]
    set_id: UUID, draft_id: UUID, db: Session
) -> models.Set:
    """Commit a draft set."""
