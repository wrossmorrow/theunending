"""Settings for the Unending Admin API."""

from pydantic_settings import BaseSettings

from api.database.models import DraftStatus, RunStatus, RunType, SetStatus


class Settings(BaseSettings):
    """Settings for the Unending Admin API."""

    set_status: SetStatus = SetStatus.DRAFT
    draft_status: DraftStatus = DraftStatus.PENDING
    run_type: RunType = RunType.EVALUATION
    run_status: RunStatus = RunStatus.PENDING
    database_url: str = "sqlite+aiosqlite:///./theunending_admin.db"
    job_base_url: str = "http://localhost:8080"


settings = Settings()
