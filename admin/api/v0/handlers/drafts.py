"""Draft route handlers."""

from uuid import UUID

from fastapi import HTTPException
from fastapi import status as http_status
from sqlmodel import Session

from api.database import models as database
from api.v0.schema import models


async def create_draft(
    set_id: UUID, body: models.DraftCreate, db: Session
) -> database.Draft:
    """Create a set draft; set must exist and be DRAFT; prompt required."""
    raise HTTPException(
        status_code=http_status.HTTP_501_NOT_IMPLEMENTED,
        detail="Draft creation is not implemented yet.",
    )


async def list_drafts(set_id: UUID, db: Session) -> models.DraftsResponse:
    """List set drafts (created_at desc)."""
    raise HTTPException(
        status_code=http_status.HTTP_501_NOT_IMPLEMENTED,
        detail="Draft listing is not implemented yet.",
    )


async def get_draft(set_id: UUID, draft_id: UUID, db: Session) -> database.Draft:
    """Get a specific set draft (or 404)."""
    raise HTTPException(
        status_code=http_status.HTTP_501_NOT_IMPLEMENTED,
        detail="Draft retrieval is not implemented yet.",
    )


async def commit_draft(set_id: UUID, draft_id: UUID, db: Session) -> database.Set:
    """Commit a draft set."""
    raise HTTPException(
        status_code=http_status.HTTP_501_NOT_IMPLEMENTED,
        detail="Draft commit is not implemented yet.",
    )
