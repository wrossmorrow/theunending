"""Set API routes for the Unending Admin API."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from api.database import models as database
from api.v0.handlers import sets as sets_handlers
from api.v0.handlers.db import get_db
from api.v0.schema import models

sets_router = APIRouter()


@sets_router.get(
    "/sets", response_model=models.SetsResponse, status_code=status.HTTP_200_OK
)
async def list_sets(
    db: Annotated[Session, Depends(get_db)],
    status: database.SetStatus | None = None,
    post_date: str | None = None,
    slug: str | None = None,
    name: str | None = None,
) -> models.SetsResponse:
    """List sets with query filters."""
    return await sets_handlers.list_sets(
        status=status, post_date=post_date, slug=slug, name=name, db=db
    )


@sets_router.post(
    "/sets", response_model=database.Set, status_code=status.HTTP_201_CREATED
)
async def create_set(
    body: models.SetCreate, db: Annotated[Session, Depends(get_db)]
) -> database.Set:
    """Create a set (DRAFT status); requires model, optional slug/name."""
    return await sets_handlers.create_set(body=body, db=db)


@sets_router.get(
    "/sets/{set_id}", response_model=database.Set, status_code=status.HTTP_200_OK
)
async def get_set(
    set_id: UUID, db: Annotated[Session, Depends(get_db)]
) -> database.Set:
    """Get one set (or 404)."""
    return await sets_handlers.get_set(set_id=set_id, db=db)


@sets_router.patch(
    "/sets/{set_id}", response_model=database.Set, status_code=status.HTTP_200_OK
)
async def patch_set(
    set_id: UUID, update: models.SetUpdate, db: Annotated[Session, Depends(get_db)]
) -> database.Set:
    """Update set fields (only slug/name; DRAFT only)."""
    return await sets_handlers.patch_set(set_id=set_id, update=update, db=db)


@sets_router.delete(
    "/sets/{set_id}", response_model=database.Set, status_code=status.HTTP_200_OK
)
async def delete_set(
    set_id: UUID, db: Annotated[Session, Depends(get_db)]
) -> database.Set:
    """Mark set ABANDONED (soft; DRAFT only)."""
    return await sets_handlers.delete_set(set_id=set_id, db=db)
