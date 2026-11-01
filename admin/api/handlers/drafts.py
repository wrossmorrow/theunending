"""Draft route handlers."""

from uuid import UUID

from fastapi import HTTPException
from fastapi import status as http_status
from sqlmodel import Session

from api import models


def create_draft(set_id: UUID, body: models.DraftCreate, db: Session) -> models.Draft:
    """Create a set draft; set must exist and be DRAFT; prompt required."""
    raise HTTPException(
        status_code=http_status.HTTP_501_NOT_IMPLEMENTED,
        detail="Draft creation is not implemented yet.",
    )


def list_drafts(set_id: UUID, db: Session) -> models.DraftsResponse:
    """List set drafts (created_at desc)."""
    raise HTTPException(
        status_code=http_status.HTTP_501_NOT_IMPLEMENTED,
        detail="Draft listing is not implemented yet.",
    )


def get_draft(set_id: UUID, draft_id: UUID, db: Session) -> models.Draft:
    """Get a specific set draft (or 404)."""
    raise HTTPException(
        status_code=http_status.HTTP_501_NOT_IMPLEMENTED,
        detail="Draft retrieval is not implemented yet.",
    )


def commit_draft(set_id: UUID, draft_id: UUID, db: Session) -> models.Set:
    """Commit a draft set."""
    raise HTTPException(
        status_code=http_status.HTTP_501_NOT_IMPLEMENTED,
        detail="Draft commit is not implemented yet.",
    )
