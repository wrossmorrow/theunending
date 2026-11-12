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
    aws_region_name: str = "us-east-1"
    sns_topic_arn: str = ""

    queue_timeout_seconds: float = 30
    submit_timeout_seconds: float = 60
    max_attempts: int = 3

    supported_models: list[str] = [
        "black-forest-labs/FLUX.2-klein-4B",
        "black-forest-labs/flux-3-image-klein",
        "black-forest-labs/FLUX.1-schnell",
    ]

    publish_private_subnet_ids: list[str] = []
    publish_security_group_id: str = ""
    publish_ecs_cluster: str = "theunending-publish"
    publish_container: str = "publish"
    publish_task_family: str = "theunending-publish"


settings = Settings()
