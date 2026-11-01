"""Database dependency for API handlers."""

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    """Return the application-scoped database session factory."""
    return request.app.state.session_factory
