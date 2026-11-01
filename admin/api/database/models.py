"""Database models for the Unending Admin API."""

from datetime import UTC, datetime
from enum import Enum
from uuid import UUID, uuid7

from sqlmodel import Field, SQLModel


class SetStatus(str, Enum):
    DRAFT = "DRAFT"
    ABANDONED = "ABANDONED"
    COMMITTED = "COMMITTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class DraftStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"


class RunType(str, Enum):
    EVALUATION = "EVALUATION"
    BATCH = "BATCH"


class RunStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"


class Set(SQLModel, table=True):
    """A named container for many images (thousands)."""

    __tablename__ = "sets"

    set_id: UUID = Field(default_factory=uuid7, primary_key=True)
    model: str = Field(index=True)
    slug: str | None = Field(default=None, index=True)
    name: str | None = Field(default=None)
    prompt: str | None = Field(default=None)
    model_prompt_hash: str | None = Field(default=None, index=True)
    post_date: str | None = Field(default=None)
    status: SetStatus = Field(default=SetStatus.DRAFT)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    committed_at: datetime | None = Field(default=None)
    abandoned_at: datetime | None = Field(default=None)


class Draft(SQLModel, table=True):
    """A draft is a way to evaluate options before committing a set."""

    __tablename__ = "drafts"

    draft_id: UUID = Field(default_factory=uuid7, primary_key=True)
    set_id: UUID = Field(index=True)
    prompt: str = Field()
    model_prompt_hash: str = Field(index=True)
    status: DraftStatus = Field(default=DraftStatus.PENDING)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Run(SQLModel, table=True):
    """A run tracks an external job for a set/draft."""

    __tablename__ = "runs"

    run_id: UUID = Field(default_factory=uuid7, primary_key=True)
    external_run_id: str = Field()
    set_id: UUID = Field(index=True)
    draft_id: UUID = Field(index=True)
    type: RunType = Field()
    status: RunStatus = Field(default=RunStatus.PENDING)
    details: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = Field(default=None)
