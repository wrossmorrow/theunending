"""Database dependency for API handlers."""

from fastapi import Request
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session


def get_session_factory(request: Request) -> sessionmaker[Session]:
    """Return the application-scoped database session factory."""
    return request.app.state.session_factory
