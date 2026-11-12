"""Model route handlers."""

from api.settings import settings
from api.v0.schema import models


async def list_models() -> models.ModelsResponse:
    """List supported models."""
    return models.ModelsResponse(models=list(settings.supported_models))
