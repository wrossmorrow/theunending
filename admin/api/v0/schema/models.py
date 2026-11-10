"""API request/response schemas for the Unending Admin API."""

from typing import Any, Self

from pydantic import BaseModel, Field, model_validator

from api.database.models import (
    Draft,
    Run,
    RunStatus,
    RunStatusEvent,
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


class RunStatusEventsResponse(BaseModel):
    """Response wrapper: a collection of run status events."""

    events: list[RunStatusEvent] = Field(default_factory=list)


class SetCreate(BaseModel):
    """Create a set; requires model, optional slug/name."""

    model: str = Field(min_length=1)
    slug: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9-]{1,126}[a-z]$")
    name: str | None = Field(default=None, max_length=64, min_length=1)


class DraftCreate(BaseModel):
    """Create a draft; prompt required."""

    prompt: str = Field(min_length=1, max_length=1023)


class DraftFromPromptCreate(DraftCreate):
    """Create a draft set (and its first draft) from a submitted prompt idea.

    The submitted human title becomes the set name; the set slug is derived from
    it server-side so free-form titles still land in a valid slug.
    """

    name: str = Field(min_length=1, max_length=64)
    model: str | None = Field(default=None, min_length=1)


class SetUpdate(BaseModel):
    """Update a set; only slug and name may be changed."""

    slug: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9-]{1,126}[a-z]$")
    name: str | None = Field(default=None, max_length=64, min_length=1)

    @model_validator(mode="after")
    def validate_at_least_one(self) -> Self:
        """Require at least one of slug or name to be provided."""
        if self.slug is None and self.name is None:
            raise ValueError("At least one of 'slug' or 'name' must be provided.")
        return self


class PublishSetBody(BaseModel):
    """Publish a set; optional extra details added to the post draft."""

    extra_details: str | None = Field(default=None, max_length=512)


class RunStatusUpdate(BaseModel):
    """Update a run status."""

    status: RunStatus = Field()
    message: str | None = Field(default=None, max_length=1024)
    details: dict[str, Any] | None = Field(default=None)


class DraftPreviewResponse(BaseModel):
    """Preview response: presigned S3 URL for a completed draft's image."""

    preview_url: str
