"""Settings for the Unending Admin API."""

from pydantic_settings import BaseSettings

from api import models


class Settings(BaseSettings):
    """Settings for the Unending Admin API."""

    set_status: models.SetStatus = models.SetStatus.DRAFT
    draft_status: models.DraftStatus = models.DraftStatus.PENDING
    run_type: models.RunType = models.RunType.EVALUATION
    run_status: models.RunStatus = models.RunStatus.PENDING
    database_url: str = "sqlite:///./theunending_admin.db"
