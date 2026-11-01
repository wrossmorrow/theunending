"""Database dependency for API handlers."""

from collections.abc import Iterator

from fastapi import Request
from sqlmodel import Session


def get_db(request: Request) -> Iterator[Session]:
    """Inject a database session from the app-scoped engine."""
    engine = request.app.state.engine
    with Session(engine) as session:
        yield session
