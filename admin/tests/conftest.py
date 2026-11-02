import asyncio
import sys
from collections.abc import Generator
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel

from api.settings import settings


@pytest.fixture(scope="session", autouse=True)
def create_test_db() -> Generator[None]:
    """Create the SQLite database schema for the test session, then clean up."""
    engine = create_async_engine(settings.database_url)

    async def _create() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(SQLModel.metadata.create_all)

    asyncio.run(_create())

    yield

    async def _drop() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(SQLModel.metadata.drop_all)

    asyncio.run(_drop())
