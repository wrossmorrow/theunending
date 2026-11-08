"""Unit tests for the SNS run notification subject and email body."""

from datetime import UTC, datetime
from uuid import uuid4

from api.database import models as database
from api.settings import settings
from api.utils.notifications import (
    SNS_SUBJECT_MAX_LENGTH,
    RunNotification,
    build_run_notification,
    format_duration,
    run_email_body,
    run_subject,
    set_title,
)


def _notification(
    *,
    run_type: database.RunType = database.RunType.PUBLISH,
    status: database.RunStatus = database.RunStatus.COMPLETED,
    set_name: str | None = "Waiting Stained Glass",
    set_slug: str | None = "waiting-stained-glass",
    set_model: str | None = "black-forest-labs/FLUX.2-klein-4B",
    set_prompt: str | None = "a stained glass window of a cat",
    message: str | None = "all content prepared and uploaded to S3",
    details: dict | None = None,
) -> RunNotification:
    """Build a notification for subject and body assertions."""
    return RunNotification(
        run_id=uuid4(),
        set_id=uuid4(),
        draft_id=uuid4(),
        run_type=run_type,
        status=status,
        message=message,
        details=details,
        set_name=set_name,
        set_slug=set_slug,
        set_model=set_model,
        set_prompt=set_prompt,
        run_created_at=datetime(2026, 11, 8, 12, 0, 0, tzinfo=UTC),
        run_submitted_at=datetime(2026, 11, 8, 12, 5, 0, tzinfo=UTC),
        run_finished_at=datetime(2026, 11, 8, 13, 0, 0, tzinfo=UTC),
    )


def test_run_subject_includes_set_title_run_and_status() -> None:
    """The subject is the theunending prefix, set title, run type and run status."""
    notification = _notification()
    assert (
        run_subject(notification)
        == "theunending: Waiting Stained Glass (waiting-stained-glass) run PUBLISH COMPLETED"
    )


def test_run_subject_without_set_falls_back_to_untitled() -> None:
    """The subject falls back to an untitled set when no set details exist."""
    notification = _notification(set_name=None, set_slug=None)
    assert (
        run_subject(notification) == "theunending: Untitled set run PUBLISH COMPLETED"
    )


def test_run_subject_truncates_to_sns_max_length() -> None:
    """The subject never exceeds the SNS subject limit."""
    notification = _notification(set_name="x" * 64, set_slug="y" * 128)
    subject = run_subject(notification)
    assert len(subject) <= SNS_SUBJECT_MAX_LENGTH


def test_set_title_includes_name_and_slug() -> None:
    """The set title is the name with the slug in parentheses when both exist."""
    assert set_title(_notification()) == "Waiting Stained Glass (waiting-stained-glass)"
    assert set_title(_notification(set_name=None, set_slug="only-slug")) == "only-slug"


def test_run_email_body_includes_set_details_and_timing() -> None:
    """The email body includes set and run details, and links to the admin set page."""
    notification = _notification()
    body = run_email_body(notification)
    assert "Run type: PUBLISH" in body
    assert "Run status: COMPLETED" in body
    assert "Set details:" in body
    assert "Name: Waiting Stained Glass" in body
    assert "Slug: waiting-stained-glass" in body
    assert "Model: black-forest-labs/FLUX.2-klein-4B" in body
    assert "Prompt: a stained glass window of a cat" in body
    assert "Run status message:" in body
    assert "all content prepared and uploaded to S3" in body
    assert "Timing:" in body
    assert "Created: 2026-11-08 12:00:00+00:00" in body
    assert "Duration: 1h 00m" in body
    assert (
        "Admin set page:" in body
        and f"{settings.admin_base_url}/admin/#/sets/{notification.set_id}" in body
    )


def test_run_email_body_excludes_raw_details() -> None:
    """The email body does not carry the raw run status update details payload."""
    notification = _notification(details={"spec_s3_location": "s3://bucket/spec.json"})
    body = run_email_body(notification)
    assert "s3://bucket/spec.json" not in body
    assert "spec_s3_location" not in body


def test_format_duration_returns_human_readable_duration() -> None:
    """Duration is rendered as seconds, minutes or hours."""
    assert format_duration(None, None) == "—"
    assert (
        format_duration(
            datetime(2026, 11, 8, 12, 0, 0), datetime(2026, 11, 8, 12, 0, 30)
        )
        == "30s"
    )
    assert (
        format_duration(
            datetime(2026, 11, 8, 12, 0, 0), datetime(2026, 11, 8, 12, 5, 0)
        )
        == "5m 00s"
    )
    assert (
        format_duration(
            datetime(2026, 11, 8, 12, 0, 0), datetime(2026, 11, 8, 14, 30, 0)
        )
        == "2h 30m"
    )


def test_build_run_notification_extracts_set_and_timing_fields() -> None:
    """The notification carries the linked set details and run timings."""
    set_ = database.Set(
        model="black-forest-labs/FLUX.2-klein-4B",
        slug="waiting-stained-glass",
        name="Waiting Stained Glass",
        prompt="a stained glass window of a cat",
    )
    run = database.Run(
        external_run_id=None,
        set_id=set_.set_id,
        draft_id=uuid4(),
        type=database.RunType.PUBLISH,
        status=database.RunStatus.COMPLETED,
    )
    notification = build_run_notification(run, database.RunStatus.COMPLETED, set_=set_)
    assert notification.set_name == "Waiting Stained Glass"
    assert notification.set_slug == "waiting-stained-glass"
    assert notification.set_model == "black-forest-labs/FLUX.2-klein-4B"
    assert notification.set_prompt == "a stained glass window of a cat"
