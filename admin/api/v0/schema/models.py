"""API request/response schemas for the Unending Admin API."""

from sqlmodel import Field, SQLModel

from api.database.models import (
    Draft,
    Run,
    RunStatus,
    Set,
)


class SetsResponse(SQLModel, table=False):
    """Response wrapper: a collection of sets."""

    sets: list[Set] = Field(default_factory=list)


class DraftsResponse(SQLModel, table=False):
    """Response wrapper: a collection of drafts."""

    drafts: list[Draft] = Field(default_factory=list)


class RunsResponse(SQLModel, table=False):
    """Response wrapper: a collection of runs."""

    runs: list[Run] = Field(default_factory=list)


class SetCreate(SQLModel, table=False):
    """Create a set; requires model, optional slug/name."""

    model: str = Field()
    slug: str | None = Field(default=None)
    name: str | None = Field(default=None)


class DraftCreate(SQLModel, table=False):
    """Create a draft; prompt required."""

    prompt: str = Field()


class SetUpdate(SQLModel, table=False):
    """Update a set; only slug and name may be changed."""

    slug: str | None = Field(default=None)
    name: str | None = Field(default=None)


class RunStatusUpdate(SQLModel, table=False):
    """Update a run status."""

    status: RunStatus = Field()
