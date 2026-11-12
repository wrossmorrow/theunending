"""Model API routes for the Unending Admin API."""

from fastapi import APIRouter, status

from api.v0.handlers import models as models_handlers
from api.v0.schema import models as models_schema

models_router = APIRouter()


@models_router.get(
    "/models",
    response_model=models_schema.ModelsResponse,
    status_code=status.HTTP_200_OK,
)
async def list_models() -> models_schema.ModelsResponse:
    """List supported models."""
    return await models_handlers.list_models()
