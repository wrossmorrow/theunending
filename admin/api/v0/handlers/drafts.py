"""Draft route handlers."""

from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy import exc as sqlalchemy_exc
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import select

from api.database import models as database
from api.settings import settings
from api.utils.jobs import ExternalJobClient, JobParameters, JobRequest
from api.utils.prompt import compute_model_prompt_hash
from api.utils.s3 import create_presigned_url
from api.v0.schema import models


async def create_draft(
    set_id: UUID,
    body: models.DraftCreate,
    session_factory: async_sessionmaker[AsyncSession],
    job_client: ExternalJobClient,
) -> database.Draft:
    """Create a set draft; set must exist and be DRAFT; prompt required."""
    async with session_factory() as session:
        table = database.Set.metadata.tables[database.Set.__tablename__]
        stmt = select(database.Set).where(table.c.set_id == set_id)
        set_ = (await session.execute(stmt)).scalars().first()
        if set_ is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Set {set_id} not found.",
            )
        if set_.status != database.SetStatus.DRAFT:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=f"Set {set_id} is not in DRAFT status.",
            )

        model = set_.model
        draft = database.Draft(
            set_id=set_.set_id,
            prompt=body.prompt,
            model_prompt_hash=compute_model_prompt_hash(model, body.prompt),
            status=database.DraftStatus.PENDING,
        )
        draft_id = draft.draft_id
        draft_model_prompt_hash = draft.model_prompt_hash
        session.add(draft)
        run = database.Run(
            external_run_id=None,
            set_id=set_id,
            draft_id=draft_id,
            type=database.RunType.EVALUATION,
            status=database.RunStatus.PENDING,
        )
        session.add(run)
        try:
            await session.commit()
            await session.refresh(draft)
            await session.refresh(run)
        except sqlalchemy_exc.IntegrityError:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="Draft prompt already exists.",
            )

        job_request = JobRequest(
            run_id=run.run_id,
            job_type=database.RunType.EVALUATION,
            job_params=JobParameters(
                model_id=model,
                s3_bucket=settings.s3_bucket_name,
                s3_prefix=f"{settings.s3_evaluate_prefix}/{draft_model_prompt_hash}",
                prompt=draft.prompt,
                status_update_url=f"{settings.admin_base_url}/api/v0/runs/{run.run_id}/status",
                status_update_admin_run_id=run.run_id,
            ),
        )
        try:
            await job_client.request_job(job_request)
        except Exception as e:
            raise HTTPException(
                status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to enqueue external job.",
            ) from e

        return draft


async def get_draft_preview(
    set_id: UUID,
    draft_id: UUID,
    session_factory: async_sessionmaker[AsyncSession],
) -> models.DraftPreviewResponse:
    """Get a presigned S3 preview URL for a completed draft."""
    async with session_factory() as session:
        table = database.Draft.metadata.tables[database.Draft.__tablename__]
        stmt = select(database.Draft).where(
            table.c.set_id == set_id,
            table.c.draft_id == draft_id,
        )
        draft = (await session.execute(stmt)).scalars().first()
        if draft is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Draft {draft_id} not found.",
            )
        if draft.status != database.DraftStatus.COMPLETED:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=f"Draft {draft_id} must be in COMPLETED status for a preview.",
            )

        runs_table = database.Run.metadata.tables[database.Run.__tablename__]
        runs_stmt = (
            select(database.Run)
            .where(
                database.Run.draft_id == draft_id,
                database.Run.status == database.RunStatus.COMPLETED,
            )
            .order_by(runs_table.c.created_at.desc())
            .limit(1)
        )
        runs = (await session.execute(runs_stmt)).scalars().all()
        run = runs[0] if runs else None
        if run is None or not run.details or not run.details.get("keys"):
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"No preview image found for draft {draft_id}.",
            )
        preview_url = create_presigned_url(
            bucket=run.details["bucket"],
            key=run.details["keys"][0],
            expires_in=settings.s3_presign_expires_seconds,
        )
        return models.DraftPreviewResponse(preview_url=preview_url)


async def list_drafts(
    set_id: UUID, session_factory: async_sessionmaker[AsyncSession]
) -> models.DraftsResponse:
    """List set drafts (created_at desc)."""
    async with session_factory() as session:
        table = database.Draft.metadata.tables[database.Draft.__tablename__]
        stmt = (
            select(database.Draft)
            .where(table.c.set_id == set_id)
            .order_by(table.c.created_at.desc())
        )
        drafts = list((await session.execute(stmt)).scalars().all())
    return models.DraftsResponse(drafts=drafts)


async def get_draft(
    set_id: UUID, draft_id: UUID, session_factory: async_sessionmaker[AsyncSession]
) -> database.Draft:
    """Get a specific set draft (or 404)."""
    async with session_factory() as session:
        table = database.Draft.metadata.tables[database.Draft.__tablename__]
        draft = (
            (
                await session.execute(
                    select(database.Draft).where(
                        table.c.set_id == set_id,
                        table.c.draft_id == draft_id,
                    )
                )
            )
            .scalars()
            .first()
        )
        if draft is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Draft {draft_id} not found.",
            )
        return draft


async def commit_draft(
    set_id: UUID,
    draft_id: UUID,
    session_factory: async_sessionmaker[AsyncSession],
    job_client: ExternalJobClient,
) -> database.Set:
    """Commit a draft set."""
    table = database.Set.metadata.tables[database.Set.__tablename__]

    async with session_factory() as session:
        set_ = (
            (
                await session.execute(
                    select(database.Set)
                    .where(
                        table.c.set_id == set_id,
                        table.c.status == database.SetStatus.DRAFT,
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .first()
        )
        if set_ is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Set {set_id} not found.",
            )
        if set_.slug is None or set_.name is None:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=f"Set {set_id} must have a slug and name before commit.",
            )

        model = set_.model
        draft = await session.get(database.Draft, draft_id)
        if draft is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Draft {draft_id} not found.",
            )
        if draft.status != database.DraftStatus.COMPLETED:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=f"Draft {draft_id} is not in COMPLETED status.",
            )

        set_.prompt = draft.prompt
        set_.post_date = (
            datetime.now(ZoneInfo("America/Los_Angeles")).date().isoformat()
        )
        set_.model_prompt_hash = draft.model_prompt_hash
        set_.committed_at = datetime.now(UTC)
        set_.status = database.SetStatus.COMMITTED

        run = database.Run(
            external_run_id=None,
            set_id=set_id,
            draft_id=draft_id,
            type=database.RunType.BATCH,
            status=database.RunStatus.PENDING,
        )
        session.add(set_)
        session.add(run)
        await session.flush()
        await session.refresh(run)

        job_request = JobRequest(
            run_id=run.run_id,
            job_type=database.RunType.BATCH,
            job_params=JobParameters(
                model_id=model,
                s3_bucket=settings.s3_bucket_name,
                s3_prefix=f"{settings.s3_batch_prefix}/{draft.model_prompt_hash}",
                prompt=draft.prompt,
                status_update_url=f"{settings.admin_base_url}/api/v0/runs/{run.run_id}/status",
                status_update_admin_run_id=run.run_id,
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
        await session.refresh(set_)
        return set_
