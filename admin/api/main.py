"""Unending Admin API."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, SQLModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.health import health_router
from api.settings import Settings
from api.v0.router import api_v0_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    engine = create_engine(settings.database_url)
    SQLModel.metadata.create_all(engine)
    app.state.engine = engine
    app.state.session_factory = sessionmaker(class_=Session, bind=engine)
    yield
    engine.dispose()


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
