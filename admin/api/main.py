"""Unending Admin API."""

from typing import Optional

from fastapi import FastAPI
from admin.api import models

app = FastAPI(title="Unending Admin API")


@app.get("/api/v0/sets")
def list_sets(
    status: Optional[str] = None,
    post_date: Optional[str] = None,
    slug: Optional[str] = None,
    name: Optional[str] = None,
) -> list[models.Set]:
    """List sets with query filters."""
    ...


@app.post("/api/v0/sets")
def create_set(model: str, slug: Optional[str] = None, name: Optional[str] = None) -> models.Set:
    """Create a set (DRAFT status); requires model, optional slug/name."""
    ...


@app.get("/api/v0/sets/{set_id}")
def get_set(set_id: str) -> models.Set:
    """Get one set (or 404)."""
    ...


@app.patch("/api/v0/sets/{set_id}")
def patch_set(set_id: str, update: models.Set) -> models.Set:
    """Update set fields (only slug/name; DRAFT only)."""
    ...


@app.delete("/api/v0/sets/{set_id}")
def delete_set(set_id: str) -> None:
    """Mark set ABANDONED (soft; DRAFT only)."""
    ...


@app.post("/api/v0/sets/{set_id}/drafts")
def create_draft(set_id: str, prompt: str) -> models.Draft:
    """Create a set draft; set must exist and be DRAFT; prompt required."""
    ...


@app.get("/api/v0/sets/{set_id}/drafts")
def list_drafts(set_id: str) -> list[models.Draft]:
    """List set drafts (created_at desc)."""
    ...


@app.get("/api/v0/sets/{set_id}/drafts/{draft_id}")
def get_draft(set_id: str, draft_id: str) -> models.Draft:
    """Get a specific set draft (or 404)."""
    ...


@app.post("/api/v0/sets/{set_id}/drafts/{draft_id}/commit")
def commit_draft(set_id: str, draft_id: str) -> models.Set:
    """Commit a draft set."""
    ...


@app.get("/api/v0/runs")
def list_runs(status: Optional[str] = None, set_id: Optional[str] = None, draft_id: Optional[str] = None) -> list[models.Run]:
    """List runs with query filters."""
    ...


@app.get("/api/v0/runs/{run_id}")
def get_run(run_id: str) -> models.Run:
    """Get a specific run by id alone (or 404)."""
    ...


@app.post("/api/v0/runs/{run_id}")
def redo_run(run_id: str) -> models.Run:
    """Redo a run (requires FAILED status; creates a distinct run)."""
    ...


@app.put("/api/v0/runs/{run_id}/status")
def update_run_status(run_id: str, status: str) -> models.Run:
    """Update a run status (system call)."""
    ...
