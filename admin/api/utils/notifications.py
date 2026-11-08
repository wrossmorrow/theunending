"""SNS notifications for terminal run status updates."""

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import boto3  # type: ignore[import-untyped]
from fastapi import Request
from pydantic import BaseModel

from api.database import models as database
from api.settings import settings

SNS_SUBJECT_MAX_LENGTH = 100


class RunNotification(BaseModel):
    """A run status notification payload published to SNS for admin email subscribers."""

    run_id: UUID
    set_id: UUID
    draft_id: UUID
    run_type: database.RunType
    status: database.RunStatus
    message: str | None = None
    details: dict[str, Any] | None = None
    set_name: str | None = None
    set_slug: str | None = None
    set_model: str | None = None
    set_prompt: str | None = None
    run_created_at: datetime | None = None
    run_submitted_at: datetime | None = None
    run_finished_at: datetime | None = None


def should_notify(run_type: database.RunType, status: database.RunStatus) -> bool:
    """Return whether a run status should trigger an admin notification."""
    return run_type in (
        database.RunType.BATCH,
        database.RunType.PUBLISH,
    ) and status in (database.RunStatus.COMPLETED, database.RunStatus.FAILED)


def build_run_notification(
    run: database.Run,
    status: database.RunStatus,
    message: str | None = None,
    details: dict[str, Any] | None = None,
    set_: database.Set | None = None,
) -> RunNotification:
    """Build the notification payload for a run status update."""
    return RunNotification(
        run_id=run.run_id,
        set_id=run.set_id,
        draft_id=run.draft_id,
        run_type=run.type,
        status=status,
        message=message,
        details=details,
        set_name=set_.name if set_ is not None else None,
        set_slug=set_.slug if set_ is not None else None,
        set_model=set_.model if set_ is not None else None,
        set_prompt=set_.prompt if set_ is not None else None,
        run_created_at=run.created_at,
        run_submitted_at=run.submitted_at,
        run_finished_at=run.finished_at,
    )


def set_title(notification: RunNotification) -> str:
    """Return the human-facing set title (name with slug) for a notification."""
    if notification.set_name and notification.set_slug:
        return f"{notification.set_name} ({notification.set_slug})"
    if notification.set_name:
        return notification.set_name
    if notification.set_slug:
        return notification.set_slug
    return "Untitled set"


def run_subject(notification: RunNotification) -> str:
    """Return the SNS subject line for a run notification."""
    suffix = f" run {notification.run_type.value} {notification.status.value}"
    budget = SNS_SUBJECT_MAX_LENGTH - len("theunending: ") - len(suffix)
    title = set_title(notification)
    if len(title) > budget:
        title = title[: max(budget - 1, 0)].rstrip() + "…"
    return f"theunending: {title}{suffix}"


def format_duration(start: datetime | None, end: datetime | None) -> str:
    """Return a human-readable duration between two timestamps, or an em dash."""
    if start is None:
        return "—"
    end = end if end is not None else datetime.now(UTC)
    if (start.tzinfo is None) != (end.tzinfo is None):
        # Normalize mixed naive/aware timestamps so the subtraction is valid.
        if start.tzinfo is None:
            end = end.replace(tzinfo=None)
        else:
            start = start.replace(tzinfo=None)
    seconds = max(0, int((end - start).total_seconds()))
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def run_email_body(notification: RunNotification) -> str:
    """Return the plain-text email body for a run notification."""
    lines = [
        "theunending: run status notification",
        "",
        f"Run type: {notification.run_type.value}",
        f"Run status: {notification.status.value}",
        f"Run ID: {notification.run_id}",
        f"Set ID: {notification.set_id}",
        f"Draft ID: {notification.draft_id}",
        "",
        "Set details:",
        f"  Name: {notification.set_name or '—'}",
        f"  Slug: {notification.set_slug or '—'}",
        f"  Model: {notification.set_model or '—'}",
        f"  Prompt: {notification.set_prompt or '—'}",
        "",
        "Run status message:",
        f"  {notification.message or '—'}",
        "",
        "Timing:",
        f"  Created: {notification.run_created_at or '—'}",
        f"  Submitted: {notification.run_submitted_at or '—'}",
        f"  Finished: {notification.run_finished_at or '—'}",
        f"  Duration: {format_duration(notification.run_created_at, notification.run_finished_at)}",
        "",
        "Admin set page:",
        f"{settings.admin_base_url}/admin/#/sets/{notification.set_id}",
    ]
    return "\n".join(lines)


class SnsNotifier:
    """Publishes SNS notifications to the configured admin email topic."""

    def __init__(self, topic_arn: str = "", region_name: str = "") -> None:
        """Create a notifier for the given SNS topic (defaults to the configured region)."""
        self._topic_arn = topic_arn
        self._client = boto3.client(
            "sns", region_name=region_name or settings.aws_region_name
        )

    def publish(self, notification: RunNotification) -> str | None:
        """Publish the notification message to the SNS topic; log and swallow failures."""
        if not self._topic_arn:
            print(
                f"SNS topic ARN is not configured; skipping run notification for run {notification.run_id}."
            )
            return None
        try:
            response = self._client.publish(
                TopicArn=self._topic_arn,
                Message=run_email_body(notification),
                Subject=self._subject(notification),
            )
            return str(response.get("MessageId") or "")
        except Exception as e:  # noqa: BLE001
            print(
                f"Failed to publish SNS notification for run {notification.run_id}: "
                f"{e.__class__.__name__} {e}"
            )
            return None

    def _subject(self, notification: RunNotification) -> str:
        """Return the SNS subject line for a run notification."""
        return run_subject(notification)

    async def notify(self, notification: RunNotification) -> None:
        """Publish the notification on a worker thread; failures are logged, not raised."""
        await asyncio.to_thread(self.publish, notification)


def get_notifier(request: Request) -> SnsNotifier:
    """Return the SNS notifier from app state."""
    return request.app.state.notifier
