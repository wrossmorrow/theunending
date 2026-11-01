"""Set route handlers."""

from uuid import UUID

from fastapi import HTTPException
from fastapi import status as http_status
from sqlmodel import Session

from api.database import models as database
from api.v0.schema import models


async def list_sets(
    db: Session,
    status: database.SetStatus | None = None,
    post_date: str | None = None,
    slug: str | None = None,
    name: str | None = None,
) -> models.SetsResponse:
    """List sets with query filters."""
    raise HTTPException(
        status_code=http_status.HTTP_501_NOT_IMPLEMENTED,
        detail="Set listing is not implemented yet.",
    )


async def create_set(db: Session, body: models.SetCreate) -> database.Set:
    """Create a set (DRAFT status); requires model, optional slug/name."""
    raise HTTPException(
        status_code=http_status.HTTP_501_NOT_IMPLEMENTED,
        detail="Set creation is not implemented yet.",
    )


async def get_set(set_id: UUID, db: Session) -> database.Set:
    """Get one set (or 404)."""
    raise HTTPException(
        status_code=http_status.HTTP_501_NOT_IMPLEMENTED,
        detail="Set retrieval is not implemented yet.",
    )


async def patch_set(
    set_id: UUID, update: models.SetUpdate, db: Session
) -> database.Set:
    """Update set fields (only slug/name; DRAFT only)."""
    raise HTTPException(
        status_code=http_status.HTTP_501_NOT_IMPLEMENTED,
        detail="Set update is not implemented yet.",
    )


async def delete_set(set_id: UUID, db: Session) -> database.Set:
    """Mark set ABANDONED (soft; DRAFT only)."""
    raise HTTPException(
        status_code=http_status.HTTP_501_NOT_IMPLEMENTED,
        detail="Set delete is not implemented yet.",
    )
