"""Set API routes for the Unending Admin API."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.database import models as database
from api.database.db import get_session_factory
from api.v0.handlers import sets as sets_handlers
from api.v0.schema import models

sets_router = APIRouter()


@sets_router.get(
    "/sets", response_model=models.SetsResponse, status_code=status.HTTP_200_OK
)
async def list_sets(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
    status: database.SetStatus | None = None,
    post_date: str | None = None,
    slug: str | None = None,
    name: str | None = None,
) -> models.SetsResponse:
    """List sets with query filters."""
    return await sets_handlers.list_sets(
        session_factory, status=status, post_date=post_date, slug=slug, name=name
    )


@sets_router.post(
    "/sets", response_model=database.Set, status_code=status.HTTP_201_CREATED
)
async def create_set(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
    body: models.SetCreate,
) -> database.Set:
    """Create a set (DRAFT status); requires model, optional slug/name."""
    return await sets_handlers.create_set(session_factory, body=body)


@sets_router.get(
    "/sets/{set_id}", response_model=database.Set, status_code=status.HTTP_200_OK
)
async def get_set(
    set_id: UUID,
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> database.Set:
    """Get one set (or 404)."""
    return await sets_handlers.get_set(set_id, session_factory)


@sets_router.patch(
    "/sets/{set_id}", response_model=database.Set, status_code=status.HTTP_200_OK
)
async def patch_set(
    set_id: UUID,
    update: models.SetUpdate,
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> database.Set:
    """Update set fields (only slug/name; DRAFT only)."""
    return await sets_handlers.patch_set(set_id, update, session_factory)


@sets_router.delete(
    "/sets/{set_id}", response_model=database.Set, status_code=status.HTTP_200_OK
)
async def delete_set(
    set_id: UUID,
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> database.Set:
    """Mark set ABANDONED (soft; DRAFT only)."""
    return await sets_handlers.delete_set(set_id, session_factory)
