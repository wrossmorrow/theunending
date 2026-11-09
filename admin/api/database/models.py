"""Database models for the Unending Admin API."""

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid7

from sqlalchemy import DateTime
from sqlalchemy.dialects import postgresql
from sqlmodel import Column, Field, SQLModel


class SetStatus(str, Enum):
    DRAFT = "DRAFT"
    ABANDONED = "ABANDONED"
    COMMITTED = "COMMITTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PUBLISHING = "PUBLISHING"
    PUBLISHED = "PUBLISHED"


class DraftStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"
    COMMITTED = "COMMITTED"


class RunType(str, Enum):
    EVALUATION = "EVALUATION"
    BATCH = "BATCH"
    PUBLISH = "PUBLISH"


class RunStatus(str, Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    IN_PROGRESS = "IN_PROGRESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


class RunStatusEventSource(str, Enum):
    EXTERNAL = "EXTERNAL"
    INTERNAL = "INTERNAL"


class Set(SQLModel, table=True):
    """A named container for many images (thousands)."""

    __tablename__ = "sets"

    set_id: UUID = Field(default_factory=uuid7, primary_key=True)
    model: str = Field(index=True, min_length=1)
    slug: str | None = Field(
        default=None, index=True, regex=r"^[a-z][a-z0-9-]{1,126}[a-z]$"
    )
    name: str | None = Field(default=None, max_length=64, min_length=1)
    prompt: str | None = Field(default=None)
    model_prompt_hash: str | None = Field(default=None, index=True)
    post_date: str | None = Field(default=None)
    status: SetStatus = Field(default=SetStatus.DRAFT)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(
            DateTime(timezone=True),
            default=lambda: datetime.now(UTC),
            onupdate=lambda: datetime.now(UTC),
        ),
    )
    committed_at: datetime | None = Field(default=None)
    published_at: datetime | None = Field(default=None)
    abandoned_at: datetime | None = Field(default=None)


class Draft(SQLModel, table=True):
    """A draft is a way to evaluate options before committing a set."""

    __tablename__ = "drafts"

    draft_id: UUID = Field(default_factory=uuid7, primary_key=True)
    set_id: UUID = Field(index=True, foreign_key="sets.set_id")
    prompt: str = Field(min_length=1, max_length=1023)
    model_prompt_hash: str = Field(index=True, unique=True)
    status: DraftStatus = Field(default=DraftStatus.PENDING, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(
            DateTime(timezone=True),
            default=lambda: datetime.now(UTC),
            onupdate=lambda: datetime.now(UTC),
        ),
    )


class Run(SQLModel, table=True):
    """A run tracks an external job for a set/draft."""

    __tablename__ = "runs"

    run_id: UUID = Field(default_factory=uuid7, primary_key=True)
    external_run_id: str | None = Field(min_length=1)
    set_id: UUID = Field(index=True, foreign_key="sets.set_id")
    draft_id: UUID = Field(index=True, foreign_key="drafts.draft_id")
    type: RunType = Field(index=True)
    status: RunStatus = Field(default=RunStatus.PENDING)
    message: str | None = Field(default=None, max_length=1024)
    details: dict[str, Any] | None = Field(default=None, sa_type=postgresql.JSONB)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(
            DateTime(timezone=True),
            default=lambda: datetime.now(UTC),
            onupdate=lambda: datetime.now(UTC),
        ),
    )
    finished_at: datetime | None = Field(default=None)
    submitted_at: datetime | None = Field(default=None)


class RunStatusEvent(SQLModel, table=True):
    """A run status update payload received from an external status call."""

    __tablename__ = "run_status_events"

    event_id: UUID = Field(default_factory=uuid7, primary_key=True)
    run_id: UUID = Field(index=True, foreign_key="runs.run_id")
    status: RunStatus = Field()
    message: str | None = Field(default=None, max_length=1024)
    details: dict[str, Any] | None = Field(default=None, sa_type=postgresql.JSONB)
    source: RunStatusEventSource = Field(default=RunStatusEventSource.EXTERNAL)
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
