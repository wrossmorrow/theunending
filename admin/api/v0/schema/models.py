"""API request/response schemas for the Unending Admin API."""

from typing import Self

from pydantic import BaseModel, Field, model_validator

from api.database.models import (
    Draft,
    Run,
    RunStatus,
    Set,
)


class SetsResponse(BaseModel):
    """Response wrapper: a collection of sets."""

    sets: list[Set] = Field(default_factory=list)


class DraftsResponse(BaseModel):
    """Response wrapper: a collection of drafts."""

    drafts: list[Draft] = Field(default_factory=list)


class RunsResponse(BaseModel):
    """Response wrapper: a collection of runs."""

    runs: list[Run] = Field(default_factory=list)


class SetCreate(BaseModel):
    """Create a set; requires model, optional slug/name."""

    model: str = Field(min_length=1)
    slug: str | None = Field(default=None)
    name: str | None = Field(default=None)


class DraftCreate(BaseModel):
    """Create a draft; prompt required."""

    prompt: str = Field(min_length=1, max_length=1023)


class SetUpdate(BaseModel):
    """Update a set; only slug and name may be changed."""

    slug: str | None = Field(default=None)
    name: str | None = Field(default=None)

    @model_validator(mode="after")
    def validate_at_least_one(self) -> Self:
        """Require at least one of slug or name to be provided."""
        if self.slug is None and self.name is None:
            raise ValueError("At least one of 'slug' or 'name' must be provided.")
        return self


class RunStatusUpdate(BaseModel):
    """Update a run status."""

    status: RunStatus = Field()
