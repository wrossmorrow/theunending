"""Run route handlers."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import select

from api.database import models as database
from api.settings import settings
from api.utils.jobs import ExternalJobClient, JobParameters, JobRequest
from api.utils.notifications import (
    RunNotification,
    SnsNotifier,
    build_run_notification,
    should_notify,
)
from api.utils.publish import Publisher, PublishRequest
from api.v0.schema import models


async def list_runs(
    session_factory: async_sessionmaker[AsyncSession],
    status: database.RunStatus | None = None,
    run_type: database.RunType | None = None,
    set_id: UUID | None = None,
    draft_id: UUID | None = None,
) -> models.RunsResponse:
    """List runs with query filters."""
    async with session_factory() as session:
        table = database.Run.metadata.tables[database.Run.__tablename__]
        stmt = select(database.Run)
        if status is not None:
            stmt = stmt.where(table.c.status == status)
        if run_type is not None:
            stmt = stmt.where(table.c.type == run_type)
        if set_id is not None:
            stmt = stmt.where(table.c.set_id == set_id)
        if draft_id is not None:
            stmt = stmt.where(table.c.draft_id == draft_id)
        runs = list((await session.execute(stmt)).scalars().all())
    return models.RunsResponse(runs=runs)


async def get_run(
    run_id: UUID, session_factory: async_sessionmaker[AsyncSession]
) -> database.Run:
    """Get a specific run by id alone (or 404)."""
    async with session_factory() as session:
        run = await session.get(database.Run, run_id)
        if run is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Run {run_id} not found.",
            )
        return run


async def list_run_status_events(
    run_id: UUID, session_factory: async_sessionmaker[AsyncSession]
) -> models.RunStatusEventsResponse:
    """List the status events stored for a run (or 404)."""
    async with session_factory() as session:
        runs_table = database.Run.metadata.tables[database.Run.__tablename__]
        run = (
            (
                await session.execute(
                    select(database.Run).where(runs_table.c.run_id == run_id)
                )
            )
            .scalars()
            .first()
        )
        if run is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Run {run_id} not found.",
            )
        events_table = database.RunStatusEvent.metadata.tables[
            database.RunStatusEvent.__tablename__
        ]
        events_stmt = (
            select(database.RunStatusEvent)
            .where(events_table.c.run_id == run_id)
            .order_by(events_table.c.received_at)
        )
        events = list((await session.execute(events_stmt)).scalars().all())
    return models.RunStatusEventsResponse(events=events)


async def redo_run(
    run_id: UUID,
    session_factory: async_sessionmaker[AsyncSession],
    job_client: ExternalJobClient,
    publisher: Publisher,
) -> database.Run:
    """Redo a run (requires FAILED or CANCELLED status; creates a distinct run)."""
    async with session_factory() as session:
        runs_table = database.Run.metadata.tables[database.Run.__tablename__]
        run = (
            (
                await session.execute(
                    select(database.Run)
                    .where(runs_table.c.run_id == run_id)
                    .with_for_update()
                )
            )
            .scalars()
            .first()
        )
        if run is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Run {run_id} not found.",
            )
        if run.status not in (
            database.RunStatus.FAILED,
            database.RunStatus.CANCELLED,
        ):
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=f"Run {run_id} is not in FAILED or CANCELLED status.",
            )
        draft = await session.get(database.Draft, run.draft_id)
        if draft is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Draft {run.draft_id} not found.",
            )
        set_ = await session.get(database.Set, run.set_id)
        if set_ is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Set {run.set_id} not found.",
            )

        model = set_.model

        new_run = database.Run(
            external_run_id=None,
            set_id=run.set_id,
            draft_id=run.draft_id,
            type=run.type,
            status=database.RunStatus.PENDING,
        )
        session.add(new_run)
        await session.flush()
        await session.refresh(new_run)

        if run.type == database.RunType.PUBLISH:
            # PUBLISH runs launch an ECS Fargate task via the publisher worker rather
            # than through the external job system queue, so redo re-enqueues the publish
            # task for the new run instead of submitting an external job.
            await publisher.put(
                PublishRequest(
                    set_id=run.set_id,
                    draft_id=run.draft_id,
                    run_id=new_run.run_id,
                )
            )
            set_.updated_at = datetime.now(UTC)
            set_.status = database.SetStatus.PUBLISHING
            session.add(set_)
            await session.commit()
            await session.refresh(new_run)
            return new_run

        job_request = JobRequest(
            run_id=new_run.run_id,
            job_type=run.type,
            job_params=JobParameters(
                model_id=model,
                s3_bucket=settings.s3_bucket_name,
                s3_prefix=(
                    f"{settings.s3_evaluate_prefix if run.type == database.RunType.EVALUATION else settings.s3_batch_prefix}"
                    f"/{draft.model_prompt_hash}"
                ),
                prompt=draft.prompt,
                status_update_url=f"{settings.admin_base_url}/api/v0/runs/{new_run.run_id}/status",
                status_update_admin_run_id=new_run.run_id,
            ),
        )
        try:
            await job_client.request_job(job_request)
        except Exception as e:
            raise HTTPException(
                status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to enqueue external job.",
            ) from e

        await session.commit()
        await session.refresh(new_run)

    return new_run


def _run_transition_valid(
    current: database.RunStatus, next_status: database.RunStatus
) -> bool:
    """Return whether the run status transition is valid."""
    if current == next_status:
        # Same-state transitions are treated as no-op successes.
        return True
    valid_transitions: dict[database.RunStatus, tuple[database.RunStatus, ...]] = {
        database.RunStatus.PENDING: (
            database.RunStatus.SUBMITTED,
            database.RunStatus.IN_PROGRESS,
            database.RunStatus.FAILED,
        ),
        database.RunStatus.SUBMITTED: (
            database.RunStatus.IN_PROGRESS,
            database.RunStatus.FAILED,
            database.RunStatus.CANCELLED,
        ),
        database.RunStatus.IN_PROGRESS: (
            database.RunStatus.COMPLETED,
            database.RunStatus.FAILED,
            database.RunStatus.CANCELLED,
        ),
    }
    return next_status in valid_transitions.get(current, ())


async def _get_run_with_lock(session: AsyncSession, run_id: UUID) -> database.Run:
    """Fetch a run by id with a row lock, or raise 404."""
    runs_table = database.Run.metadata.tables[database.Run.__tablename__]
    run = (
        (
            await session.execute(
                select(database.Run)
                .where(runs_table.c.run_id == run_id)
                .with_for_update()
            )
        )
        .scalars()
        .first()
    )
    if run is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Run {run_id} not found.",
        )
    return run


async def _apply_status_update(
    session: AsyncSession,
    run: database.Run,
    update: models.RunStatusUpdate,
    source: database.RunStatusEventSource = database.RunStatusEventSource.EXTERNAL,
) -> database.Set | None:
    """Apply a valid run status update to a run within the caller's session."""
    if not _run_transition_valid(run.status, update.status):
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid run status transition from {run.status} to {update.status}."
            ),
        )

    session.add(
        database.RunStatusEvent(
            run_id=run.run_id,
            status=update.status,
            message=update.message,
            details=update.details,
            source=source,
            received_at=datetime.now(UTC),
        )
    )

    run.status = update.status
    run.updated_at = datetime.now(UTC)
    if update.status in (
        database.RunStatus.COMPLETED,
        database.RunStatus.FAILED,
        database.RunStatus.CANCELLED,
    ):
        run.finished_at = datetime.now(UTC)
    if update.message is not None:
        run.message = update.message
    if update.details is not None:
        run.details = update.details
    session.add(run)
    await session.commit()
    await session.refresh(run)

    run_type = run.type
    run_set_id = run.set_id
    draft = await session.get(database.Draft, run.draft_id)
    if draft is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Draft {run.draft_id} not found.",
        )

    committed_set: database.Set | None = None
    match run_type:
        case database.RunType.EVALUATION:
            if update.status != database.RunStatus.SUBMITTED:
                draft.status = (
                    database.DraftStatus.FAILED
                    if update.status == database.RunStatus.CANCELLED
                    else database.DraftStatus(update.status.value)
                )
                draft.updated_at = datetime.now(UTC)
                session.add(draft)
                await session.commit()
                await session.refresh(draft)

        case database.RunType.BATCH:
            if update.status in (
                database.RunStatus.COMPLETED,
                database.RunStatus.FAILED,
                database.RunStatus.CANCELLED,
            ):
                committed_set = await session.get(database.Set, run_set_id)
                if committed_set is not None:
                    committed_set.status = (
                        database.SetStatus.COMPLETED
                        if update.status == database.RunStatus.COMPLETED
                        else database.SetStatus.FAILED
                    )
                    session.add(committed_set)
                    await session.commit()
                    await session.refresh(committed_set)

        case database.RunType.PUBLISH:
            if update.status in (
                database.RunStatus.COMPLETED,
                database.RunStatus.FAILED,
                database.RunStatus.CANCELLED,
            ):
                committed_set = await session.get(database.Set, run_set_id)
                if committed_set is not None:
                    committed_set.status = (
                        database.SetStatus.PUBLISHED
                        if update.status == database.RunStatus.COMPLETED
                        else database.SetStatus.FAILED
                    )
                    if update.status == database.RunStatus.COMPLETED:
                        committed_set.published_at = datetime.now(UTC)
                    session.add(committed_set)
                    await session.commit()
                    await session.refresh(committed_set)

        case _:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported run type {run_type} for update.",
            )

    await session.refresh(run)
    return committed_set


async def update_run_status(
    run_id: UUID,
    update: models.RunStatusUpdate,
    session_factory: async_sessionmaker[AsyncSession],
    notifier: SnsNotifier,
) -> database.Run:
    """Update a run status (system call)."""
    notification: RunNotification | None = None
    async with session_factory() as session:
        run = await _get_run_with_lock(session, run_id)
        committed_set = await _apply_status_update(session, run, update)
        if should_notify(run.type, update.status):
            notification = build_run_notification(
                run,
                update.status,
                message=update.message,
                details=update.details,
                set_=committed_set,
            )

    # Send the notification after the status transaction commits; a failed email
    # push never fails or rolls back the status update.
    if notification is not None and notifier is not None:
        await notifier.notify(notification)

    return run


async def cancel_run(
    run_id: UUID,
    session_factory: async_sessionmaker[AsyncSession],
    job_client: ExternalJobClient,
    notifier: SnsNotifier,
) -> database.Run:
    """Cancel an external run (requires SUBMITTED or IN_PROGRESS status and an external run id)."""
    notification: RunNotification | None = None
    async with session_factory() as session:
        run = await _get_run_with_lock(session, run_id)
        if run.external_run_id is None:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=f"Run {run_id} has no external run id to cancel.",
            )
        if not _run_transition_valid(run.status, database.RunStatus.CANCELLED):
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Invalid run status transition from {run.status} to "
                    f"{database.RunStatus.CANCELLED}."
                ),
            )
        try:
            await job_client.cancel_job(run.external_run_id)
        except Exception as e:
            raise HTTPException(
                status_code=http_status.HTTP_502_BAD_GATEWAY,
                detail="Failed to cancel external job.",
            ) from e

        update = models.RunStatusUpdate(
            status=database.RunStatus.CANCELLED,
            message="cancelled by admin",
        )
        committed_set = await _apply_status_update(
            session, run, update, source=database.RunStatusEventSource.INTERNAL
        )
        if should_notify(run.type, update.status):
            notification = build_run_notification(
                run,
                update.status,
                message=update.message,
                details=update.details,
                set_=committed_set,
            )

    if notification is not None and notifier is not None:
        await notifier.notify(notification)

    return run
