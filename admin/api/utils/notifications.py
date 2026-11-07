"""SNS notifications for terminal run status updates."""

import asyncio
import json
from typing import Any
from uuid import UUID

import boto3  # type: ignore[import-untyped]
from fastapi import Request
from pydantic import BaseModel

from api.database import models as database
from api.settings import settings


class RunNotification(BaseModel):
    """A run status notification payload published to SNS for admin email subscribers."""

    run_id: UUID
    set_id: UUID
    draft_id: UUID
    run_type: database.RunType
    status: database.RunStatus
    message: str | None = None
    details: dict[str, Any] | None = None


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
    )


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
                Message=json.dumps(notification.model_dump(mode="json")),
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
        return f"theunending: {notification.run_type} run {notification.status}"

    async def notify(self, notification: RunNotification) -> None:
        """Publish the notification on a worker thread; failures are logged, not raised."""
        await asyncio.to_thread(self.publish, notification)


def get_notifier(request: Request) -> SnsNotifier:
    """Return the SNS notifier from app state."""
    return request.app.state.notifier
