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
    admin_base_url: str = "http://localhost:8000"
    job_base_url: str = "http://localhost:8080"
    job_bearer_token: str = "dev-token"
    s3_bucket_name: str = "unending-local"
    s3_evaluate_prefix: str = "drafts"
    s3_batch_prefix: str = "runs"
    s3_presign_expires_seconds: int = 300


settings = Settings()
