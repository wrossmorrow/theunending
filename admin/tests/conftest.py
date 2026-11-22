import asyncio
import json
import os
import sys
from collections.abc import Generator
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# The app refuses to start without a machine-auth key; provide a syntactically
# valid dummy key for the test session (no network calls happen with it).
def _test_machine_key() -> str:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()
    return json.dumps(
        {
            "type": "service_account",
            "private_key": pem,
            "private_key_id": "test-kid-123",
            "client_email": "test-admin@example.iam.gserviceaccount.com",
        }
    )


os.environ.setdefault("GOOGLE_SERVICE_ACCOUNT_KEY_JSON", _test_machine_key())

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from api.database.db import create_session_factory
from api.settings import settings


@pytest.fixture(scope="session", autouse=True)
def session_factory() -> Generator[async_sessionmaker[AsyncSession]]:
    """Create the SQLite database schema for the test session, then clean up."""
    engine = create_async_engine(settings.database_url)
    factory = create_session_factory(engine)

    async def _create() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(SQLModel.metadata.create_all)

    asyncio.run(_create())

    yield factory

    async def _drop() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(SQLModel.metadata.drop_all)

    asyncio.run(_drop())
