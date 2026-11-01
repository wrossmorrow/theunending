"""Unending Admin API."""

from uuid import UUID

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from api import models

api = FastAPI(title="Unending Admin API")


@api.get(
    "/api/v0/sets", response_model=models.SetsResponse, status_code=status.HTTP_200_OK
)
def list_sets(  # type: ignore[empty-body]
    status: models.SetStatus | None = None,
    post_date: str | None = None,
    slug: str | None = None,
    name: str | None = None,
) -> models.SetsResponse:
    """List sets with query filters."""


@api.post(
    "/api/v0/sets", response_model=models.Set, status_code=status.HTTP_201_CREATED
)
def create_set(  # type: ignore[empty-body]
    body: models.SetCreate,
) -> models.Set:
    """Create a set (DRAFT status); requires model, optional slug/name."""


@api.get(
    "/api/v0/sets/{set_id}", response_model=models.Set, status_code=status.HTTP_200_OK
)
def get_set(  # type: ignore[empty-body]
    set_id: UUID,
) -> models.Set:
    """Get one set (or 404)."""


@api.patch(
    "/api/v0/sets/{set_id}", response_model=models.Set, status_code=status.HTTP_200_OK
)
def patch_set(  # type: ignore[empty-body]
    set_id: UUID, update: models.Set
) -> models.Set:
    """Update set fields (only slug/name; DRAFT only)."""


@api.delete(
    "/api/v0/sets/{set_id}", response_model=models.Set, status_code=status.HTTP_200_OK
)
def delete_set(  # type: ignore[empty-body]
    set_id: UUID,
) -> models.Set:
    """Mark set ABANDONED (soft; DRAFT only)."""


@api.post(
    "/api/v0/sets/{set_id}/drafts",
    response_model=models.Draft,
    status_code=status.HTTP_201_CREATED,
)
def create_draft(  # type: ignore[empty-body]
    set_id: UUID, body: models.DraftCreate
) -> models.Draft:
    """Create a set draft; set must exist and be DRAFT; prompt required."""


@api.get(
    "/api/v0/sets/{set_id}/drafts",
    response_model=models.DraftsResponse,
    status_code=status.HTTP_200_OK,
)
def list_drafts(  # type: ignore[empty-body]
    set_id: UUID,
) -> models.DraftsResponse:
    """List set drafts (created_at desc)."""


@api.get(
    "/api/v0/sets/{set_id}/drafts/{draft_id}",
    response_model=models.Draft,
    status_code=status.HTTP_200_OK,
)
def get_draft(  # type: ignore[empty-body]
    set_id: UUID, draft_id: UUID
) -> models.Draft:
    """Get a specific set draft (or 404)."""


@api.post(
    "/api/v0/sets/{set_id}/drafts/{draft_id}/commit",
    response_model=models.Set,
    status_code=status.HTTP_200_OK,
)
def commit_draft(  # type: ignore[empty-body]
    set_id: UUID, draft_id: UUID
) -> models.Set:
    """Commit a draft set."""


@api.get(
    "/api/v0/runs", response_model=models.RunsResponse, status_code=status.HTTP_200_OK
)
def list_runs(  # type: ignore[empty-body]
    status: models.RunStatus | None = None,
    set_id: str | None = None,
    draft_id: str | None = None,
) -> models.RunsResponse:
    """List runs with query filters."""


@api.get(
    "/api/v0/runs/{run_id}", response_model=models.Run, status_code=status.HTTP_200_OK
)
def get_run(  # type: ignore[empty-body]
    run_id: UUID,
) -> models.Run:
    """Get a specific run by id alone (or 404)."""


@api.post(
    "/api/v0/runs/{run_id}",
    response_model=models.Run,
    status_code=status.HTTP_201_CREATED,
)
def redo_run(  # type: ignore[empty-body]
    run_id: UUID,
) -> models.Run:
    """Redo a run (requires FAILED status; creates a distinct run)."""


@api.put(
    "/api/v0/runs/{run_id}/status",
    response_model=models.Run,
    status_code=status.HTTP_200_OK,
)
def update_run_status(  # type: ignore[empty-body]
    run_id: UUID, update: models.RunStatusUpdate
) -> models.Run:
    """Update a run status (system call)."""


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
