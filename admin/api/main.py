"""Unending Admin API."""

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from api import models

api = FastAPI(title="Unending Admin API")


@api.get("/api/v0/sets", response_model=models.SetsResponse, status_code=status.HTTP_200_OK)
def list_sets(
    status: models.SetStatus | None = None,
    post_date: str | None = None,
    slug: str | None = None,
    name: str | None = None,
) -> models.SetsResponse:
    """List sets with query filters."""
    ...


@api.post("/api/v0/sets", response_model=models.Set, status_code=status.HTTP_201_CREATED)
def create_set(body: models.SetCreate) -> models.Set:
    """Create a set (DRAFT status); requires model, optional slug/name."""
    ...


@api.get("/api/v0/sets/{set_id}", response_model=models.Set, status_code=status.HTTP_200_OK)
def get_set(set_id: str) -> models.Set:
    """Get one set (or 404)."""
    ...


@api.patch("/api/v0/sets/{set_id}", response_model=models.Set, status_code=status.HTTP_200_OK)
def patch_set(set_id: str, update: models.Set) -> models.Set:
    """Update set fields (only slug/name; DRAFT only)."""
    ...


@api.delete("/api/v0/sets/{set_id}", response_model=models.Set, status_code=status.HTTP_200_OK)
def delete_set(set_id: str) -> models.Set:
    """Mark set ABANDONED (soft; DRAFT only)."""
    ...


@api.post("/api/v0/sets/{set_id}/drafts", response_model=models.Draft, status_code=status.HTTP_201_CREATED)
def create_draft(set_id: str, body: models.DraftCreate) -> models.Draft:
    """Create a set draft; set must exist and be DRAFT; prompt required."""
    ...


@api.get("/api/v0/sets/{set_id}/drafts", response_model=models.DraftsResponse, status_code=status.HTTP_200_OK)
def list_drafts(set_id: str) -> models.DraftsResponse:
    """List set drafts (created_at desc)."""
    ...


@api.get("/api/v0/sets/{set_id}/drafts/{draft_id}", response_model=models.Draft, status_code=status.HTTP_200_OK)
def get_draft(set_id: str, draft_id: str) -> models.Draft:
    """Get a specific set draft (or 404)."""
    ...


@api.post("/api/v0/sets/{set_id}/drafts/{draft_id}/commit", response_model=models.Set, status_code=status.HTTP_200_OK)
def commit_draft(set_id: str, draft_id: str) -> models.Set:
    """Commit a draft set."""
    ...


@api.get("/api/v0/runs", response_model=models.RunsResponse, status_code=status.HTTP_200_OK)
def list_runs(
    status: models.RunStatus | None = None,
    set_id: str | None = None,
    draft_id: str | None = None,
) -> models.RunsResponse:
    """List runs with query filters."""
    ...


@api.get("/api/v0/runs/{run_id}", response_model=models.Run, status_code=status.HTTP_200_OK)
def get_run(run_id: str) -> models.Run:
    """Get a specific run by id alone (or 404)."""
    ...


@api.post("/api/v0/runs/{run_id}", response_model=models.Run, status_code=status.HTTP_201_CREATED)
def redo_run(run_id: str) -> models.Run:
    """Redo a run (requires FAILED status; creates a distinct run)."""
    ...


@api.put("/api/v0/runs/{run_id}/status", response_model=models.Run, status_code=status.HTTP_200_OK)
def update_run_status(run_id: str, update: models.RunStatusUpdate) -> models.Run:
    """Update a run status (system call)."""
    ...


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
