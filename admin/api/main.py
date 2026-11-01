"""Unending Admin API."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.database.db import create_session_factory
from api.health import health_router
from api.settings import settings
from api.v0.router import api_v0_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    yield
    await engine.dispose()


api = FastAPI(title="Unending Admin API", lifespan=lifespan)
api.include_router(health_router)
api.include_router(api_v0_router)


@api.exception_handler(Exception)
async def _exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, (HTTPException, StarletteHTTPException)):
        raise exc

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": str(exc),
            "error_class": exc.__class__.__name__,
            "details": {"error": str(exc)},
        },
    )
