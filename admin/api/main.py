"""Unending Admin API."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import create_async_engine
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.database.db import create_session_factory, selectone
from api.health import health_router
from api.settings import settings
from api.utils.jobs import ExternalJobClient
from api.utils.notifications import SnsNotifier
from api.utils.publish import Publisher
from api.v0.router import api_v0_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    engine = create_async_engine(settings.database_url)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.notifier = SnsNotifier(topic_arn=settings.sns_topic_arn)
    app.state.job_client = ExternalJobClient(
        base_url=settings.job_base_url,
        session_factory=app.state.session_factory,
        queue_timeout_seconds=settings.queue_timeout_seconds,
        submit_timeout_seconds=settings.submit_timeout_seconds,
        max_attempts=settings.max_attempts,
        notifier=app.state.notifier,
    )
    app.state.publisher = Publisher(
        queue_timeout_seconds=settings.queue_timeout_seconds,
        max_attempts=settings.max_attempts,
        session_factory=app.state.session_factory,
        notifier=app.state.notifier,
    )
    await app.state.job_client.start()
    await app.state.publisher.start()
    await selectone(app.state.session_factory)
    yield
    await engine.dispose()
    await app.state.job_client.aclose()
    await app.state.publisher.aclose()


api = FastAPI(title="Unending Admin API", lifespan=lifespan)
api.include_router(health_router)
api.include_router(api_v0_router)

api.mount("/admin", StaticFiles(directory="web", html=True), name="admin")


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
