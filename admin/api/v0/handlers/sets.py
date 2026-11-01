"""Set route handlers."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import select

from api.database import models as database
from api.v0.schema import models


async def list_sets(
    session_factory: async_sessionmaker[AsyncSession],
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


async def create_set(
    session_factory: async_sessionmaker[AsyncSession], body: models.SetCreate
) -> database.Set:
    """Create a set (DRAFT status); requires model, optional slug/name."""
    async with session_factory() as session:
        set_ = database.Set(
            model=body.model,
            slug=body.slug,
            name=body.name,
            prompt=None,
            model_prompt_hash=None,
            status=database.SetStatus.DRAFT,
            created_at=datetime.now(UTC),
            committed_at=None,
            abandoned_at=None,
        )
        session.add(set_)
        await session.commit()
        await session.refresh(set_)
        return set_


async def get_set(
    set_id: UUID, session_factory: async_sessionmaker[AsyncSession]
) -> database.Set:
    """Get one set (or 404)."""
    raise HTTPException(
        status_code=http_status.HTTP_501_NOT_IMPLEMENTED,
        detail="Set retrieval is not implemented yet.",
    )


async def patch_set(
    set_id: UUID,
    update: models.SetUpdate,
    session_factory: async_sessionmaker[AsyncSession],
) -> database.Set:
    """Update set fields (only slug/name; DRAFT only)."""
    async with session_factory() as session:
        table = database.Set.metadata.tables[database.Set.__tablename__]
        stmt = select(database.Set).where(table.c.set_id == set_id).with_for_update()
        set_ = (await session.execute(stmt)).scalars().first()
        if set_ is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Set {set_id} not found.",
            )
        if set_.status != database.SetStatus.DRAFT:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=f"Set {set_id} is not in DRAFT status.",
            )
        set_.slug = update.slug
        set_.name = update.name
        set_.updated_at = datetime.now(UTC)
        session.add(set_)
        await session.commit()
        await session.refresh(set_)
        return set_


async def delete_set(
    set_id: UUID, session_factory: async_sessionmaker[AsyncSession]
) -> database.Set:
    """Mark set ABANDONED (soft; DRAFT only)."""
    async with session_factory() as session:
        set_ = await session.get(database.Set, set_id)
        if set_ is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Set {set_id} not found.",
            )
        if set_.status != database.SetStatus.DRAFT:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=f"Set {set_id} is not in DRAFT status.",
            )
        set_.status = database.SetStatus.ABANDONED
        set_.abandoned_at = datetime.now(UTC)
        session.add(set_)
        await session.commit()
        await session.refresh(set_)
        return set_
