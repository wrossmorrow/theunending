"""Database dependency for API handlers."""

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    """Return the application-scoped database session factory."""
    return request.app.state.session_factory


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create an application-scoped database session factory bound to an engine."""
    return async_sessionmaker(class_=AsyncSession, bind=engine)


async def selectone(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """SELECT 1 as a connection check."""
    async with session_factory() as session:
        (await session.execute(select(1))).scalar()
