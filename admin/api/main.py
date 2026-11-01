"""Unending Admin API."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, SQLModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from api import models
from api.handlers import drafts as drafts_handlers
from api.handlers import runs as runs_handlers
from api.handlers import sets as sets_handlers
from api.handlers.db import get_db
from api.settings import Settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    engine = create_engine(settings.database_url)
    SQLModel.metadata.create_all(engine)
    app.state.engine = engine
    app.state.session_factory = sessionmaker(engine, class_=SQLModel)
    yield
    engine.dispose()


api = FastAPI(title="Unending Admin API", lifespan=lifespan)


@api.get(
    "/api/v0/sets", response_model=models.SetsResponse, status_code=status.HTTP_200_OK
)
async def list_sets(
    db: Annotated[Session, Depends(get_db)],
    status: models.SetStatus | None = None,
    post_date: str | None = None,
    slug: str | None = None,
    name: str | None = None,
) -> models.SetsResponse:
    """List sets with query filters."""
    return sets_handlers.list_sets(
        status=status, post_date=post_date, slug=slug, name=name, db=db
    )


@api.post(
    "/api/v0/sets", response_model=models.Set, status_code=status.HTTP_201_CREATED
)
async def create_set(
    body: models.SetCreate, db: Annotated[Session, Depends(get_db)]
) -> models.Set:
    """Create a set (DRAFT status); requires model, optional slug/name."""
    return sets_handlers.create_set(body=body, db=db)


@api.get(
    "/api/v0/sets/{set_id}", response_model=models.Set, status_code=status.HTTP_200_OK
)
async def get_set(set_id: UUID, db: Annotated[Session, Depends(get_db)]) -> models.Set:
    """Get one set (or 404)."""
    return sets_handlers.get_set(set_id=set_id, db=db)


@api.patch(
    "/api/v0/sets/{set_id}", response_model=models.Set, status_code=status.HTTP_200_OK
)
async def patch_set(
    set_id: UUID, update: models.Set, db: Annotated[Session, Depends(get_db)]
) -> models.Set:
    """Update set fields (only slug/name; DRAFT only)."""
    return sets_handlers.patch_set(set_id=set_id, update=update, db=db)


@api.delete(
    "/api/v0/sets/{set_id}", response_model=models.Set, status_code=status.HTTP_200_OK
)
async def delete_set(
    set_id: UUID, db: Annotated[Session, Depends(get_db)]
) -> models.Set:
    """Mark set ABANDONED (soft; DRAFT only)."""
    return sets_handlers.delete_set(set_id=set_id, db=db)


@api.post(
    "/api/v0/sets/{set_id}/drafts",
    response_model=models.Draft,
    status_code=status.HTTP_201_CREATED,
)
async def create_draft(
    set_id: UUID, body: models.DraftCreate, db: Annotated[Session, Depends(get_db)]
) -> models.Draft:
    """Create a set draft; set must exist and be DRAFT; prompt required."""
    return drafts_handlers.create_draft(set_id=set_id, body=body, db=db)


@api.get(
    "/api/v0/sets/{set_id}/drafts",
    response_model=models.DraftsResponse,
    status_code=status.HTTP_200_OK,
)
async def list_drafts(
    set_id: UUID, db: Annotated[Session, Depends(get_db)]
) -> models.DraftsResponse:
    """List set drafts (created_at desc)."""
    return drafts_handlers.list_drafts(set_id=set_id, db=db)


@api.get(
    "/api/v0/sets/{set_id}/drafts/{draft_id}",
    response_model=models.Draft,
    status_code=status.HTTP_200_OK,
)
async def get_draft(
    set_id: UUID, draft_id: UUID, db: Annotated[Session, Depends(get_db)]
) -> models.Draft:
    """Get a specific set draft (or 404)."""
    return drafts_handlers.get_draft(set_id=set_id, draft_id=draft_id, db=db)


@api.post(
    "/api/v0/sets/{set_id}/drafts/{draft_id}/commit",
    response_model=models.Set,
    status_code=status.HTTP_200_OK,
)
async def commit_draft(
    set_id: UUID, draft_id: UUID, db: Annotated[Session, Depends(get_db)]
) -> models.Set:
    """Commit a draft set."""
    return drafts_handlers.commit_draft(set_id=set_id, draft_id=draft_id, db=db)


@api.get(
    "/api/v0/runs", response_model=models.RunsResponse, status_code=status.HTTP_200_OK
)
async def list_runs(
    db: Annotated[Session, Depends(get_db)],
    status: models.RunStatus | None = None,
    set_id: str | None = None,
    draft_id: str | None = None,
) -> models.RunsResponse:
    """List runs with query filters."""
    return runs_handlers.list_runs(
        status=status, set_id=set_id, draft_id=draft_id, db=db
    )


@api.get(
    "/api/v0/runs/{run_id}", response_model=models.Run, status_code=status.HTTP_200_OK
)
async def get_run(run_id: UUID, db: Annotated[Session, Depends(get_db)]) -> models.Run:
    """Get a specific run by id alone (or 404)."""
    return runs_handlers.get_run(run_id=run_id, db=db)


@api.post(
    "/api/v0/runs/{run_id}",
    response_model=models.Run,
    status_code=status.HTTP_201_CREATED,
)
async def redo_run(run_id: UUID, db: Annotated[Session, Depends(get_db)]) -> models.Run:
    """Redo a run (requires FAILED status; creates a distinct run)."""
    return runs_handlers.redo_run(run_id=run_id, db=db)


@api.put(
    "/api/v0/runs/{run_id}/status",
    response_model=models.Run,
    status_code=status.HTTP_200_OK,
)
async def update_run_status(
    run_id: UUID,
    update: models.RunStatusUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> models.Run:
    """Update a run status (system call)."""
    return runs_handlers.update_run_status(run_id=run_id, update=update, db=db)


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
