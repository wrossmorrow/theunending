"""Data models for the Unending Admin API.

Aligned with the resources in ``admin/DESIGN.md``: sets, drafts, and runs.
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

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

    set_id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    model: str = Field(index=True)
    slug: Optional[str] = Field(default=None, index=True)
    name: Optional[str] = Field(default=None)
    prompt: Optional[str] = Field(default=None)
    model_prompt_hash: str = Field(index=True)
    post_date: Optional[str] = Field(default=None)
    status: SetStatus = Field(default=SetStatus.DRAFT)
    created_at: Optional[datetime] = Field(default=None)
    updated_at: Optional[datetime] = Field(default=None)
    committed_at: Optional[datetime] = Field(default=None)
    abandoned_at: Optional[datetime] = Field(default=None)


class Draft(SQLModel, table=True):
    """A draft is a way to evaluate options before committing a set."""

    __tablename__ = "drafts"

    draft_id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    set_id: str = Field(index=True)
    prompt: str = Field()
    model_prompt_hash: str = Field(index=True)
    status: DraftStatus = Field(default=DraftStatus.PENDING)
    created_at: Optional[datetime] = Field(default=None)


class Run(SQLModel, table=True):
    """A run tracks an external job for a set/draft."""

    __tablename__ = "runs"

    run_id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    external_run_id: str = Field()
    set_id: str = Field(index=True)
    draft_id: str = Field(index=True)
    type: RunType = Field()
    status: RunStatus = Field(default=RunStatus.PENDING)
    details: Optional[str] = Field(default=None)
    created_at: Optional[datetime] = Field(default=None)
    updated_at: Optional[datetime] = Field(default=None)
    finished_at: Optional[datetime] = Field(default=None)
