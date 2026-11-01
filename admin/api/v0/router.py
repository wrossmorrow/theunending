"""Aggregated /api/v0 router for the Unending Admin API."""

from fastapi import APIRouter

from api.v0.routers import drafts, runs, sets

api_v0_router = APIRouter(prefix="/api/v0")


api_v0_router.include_router(sets.sets_router)
api_v0_router.include_router(drafts.drafts_router)
api_v0_router.include_router(runs.runs_router)
