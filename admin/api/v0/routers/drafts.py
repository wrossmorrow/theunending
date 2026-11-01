"""Draft API routes for the Unending Admin API."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session

from api.database import models as database
from api.database.db import get_session_factory
from api.utils.jobs import ExternalJobClient, get_job_client
from api.v0.handlers import drafts as drafts_handlers
from api.v0.schema import models

drafts_router = APIRouter()


@drafts_router.post(
    "/sets/{set_id}/drafts",
    response_model=database.Draft,
    status_code=status.HTTP_201_CREATED,
)
async def create_draft(
    set_id: UUID,
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
    job_client: Annotated[ExternalJobClient, Depends(get_job_client)],
    body: models.DraftCreate,
) -> database.Draft:
    """Create a set draft; set must exist and be DRAFT; prompt required."""
    return await drafts_handlers.create_draft(set_id, body, session_factory, job_client)


@drafts_router.get(
    "/sets/{set_id}/drafts",
    response_model=models.DraftsResponse,
    status_code=status.HTTP_200_OK,
)
async def list_drafts(
    set_id: UUID,
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> models.DraftsResponse:
    """List set drafts (created_at desc)."""
    return await drafts_handlers.list_drafts(set_id, session_factory)


@drafts_router.get(
    "/sets/{set_id}/drafts/{draft_id}",
    response_model=database.Draft,
    status_code=status.HTTP_200_OK,
)
async def get_draft(
    set_id: UUID,
    draft_id: UUID,
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> database.Draft:
    """Get a specific set draft (or 404)."""
    return await drafts_handlers.get_draft(set_id, draft_id, session_factory)


@drafts_router.post(
    "/sets/{set_id}/drafts/{draft_id}/commit",
    response_model=database.Set,
    status_code=status.HTTP_200_OK,
)
async def commit_draft(
    set_id: UUID,
    draft_id: UUID,
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
    job_client: Annotated[ExternalJobClient, Depends(get_job_client)],
) -> database.Set:
    """Commit a draft set."""
    return await drafts_handlers.commit_draft(
        set_id, draft_id, session_factory, job_client
    )
