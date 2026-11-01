"""Draft route handlers."""

from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, select

from api.database import models as database
from api.utils.jobs import ExternalJobClient
from api.utils.prompt import compute_model_prompt_hash
from api.v0.schema import models


async def create_draft(
    set_id: UUID,
    body: models.DraftCreate,
    session_factory: sessionmaker[Session],
    job_client: ExternalJobClient,
) -> database.Draft:
    """Create a set draft; set must exist and be DRAFT; prompt required."""
    with session_factory() as session:
        table = database.Set.metadata.tables[database.Set.__tablename__]
        stmt = select(database.Set).where(table.c.set_id == set_id).with_for_update()
        set_ = session.exec(stmt).first()
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
        if len(body.prompt) >= 1024:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="Prompt must be shorter than 1024 characters.",
            )

        draft = database.Draft(
            set_id=set_.set_id,
            prompt=body.prompt,
            model_prompt_hash=compute_model_prompt_hash(set_.model, body.prompt),
            status=database.DraftStatus.PENDING,
        )
        session.add(draft)
        session.commit()
        draft_id = draft.draft_id

    try:
        external_run_id = job_client.create_job(
            {
                "set_id": str(set_id),
                "draft_id": str(draft_id),
                "model_prompt_hash": draft.model_prompt_hash,
            }
        )
    except httpx.HTTPError, KeyError:
        with session_factory() as session:
            failed_draft = session.get(database.Draft, draft_id)
            if failed_draft is not None:
                session.delete(failed_draft)
                session.commit()
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create external job.",
        )

    with session_factory() as session:
        run = database.Run(
            external_run_id=external_run_id,
            set_id=set_id,
            draft_id=draft_id,
            type=database.RunType.EVALUATION,
            status=database.RunStatus.PENDING,
        )
        session.add(run)
        session.commit()

    return draft


async def list_drafts(
    set_id: UUID, session_factory: sessionmaker[Session]
) -> models.DraftsResponse:
    """List set drafts (created_at desc)."""
    raise HTTPException(
        status_code=http_status.HTTP_501_NOT_IMPLEMENTED,
        detail="Draft listing is not implemented yet.",
    )


async def get_draft(
    set_id: UUID, draft_id: UUID, session_factory: sessionmaker[Session]
) -> database.Draft:
    """Get a specific set draft (or 404)."""
    raise HTTPException(
        status_code=http_status.HTTP_501_NOT_IMPLEMENTED,
        detail="Draft retrieval is not implemented yet.",
    )


async def commit_draft(
    set_id: UUID,
    draft_id: UUID,
    session_factory: sessionmaker[Session],
    job_client: ExternalJobClient,
) -> database.Set:
    """Commit a draft set."""
    with session_factory() as session:
        table = database.Set.metadata.tables[database.Set.__tablename__]
        stmt = select(database.Set).where(table.c.set_id == set_id).with_for_update()
        set_ = session.exec(stmt).first()
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
        if set_.slug is None or set_.name is None:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=f"Set {set_id} must have a slug and name before commit.",
            )
        draft = session.get(database.Draft, draft_id)
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

    try:
        external_run_id = job_client.create_job(
            {
                "set_id": str(set_id),
                "draft_id": str(draft_id),
                "model_prompt_hash": draft.model_prompt_hash,
            }
        )
    except httpx.HTTPError, KeyError:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create external job.",
        )

    with session_factory() as session:
        set_ = session.exec(
            select(database.Set).where(table.c.set_id == set_id).with_for_update()
        ).first()
        if set_ is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Set {set_id} not found.",
            )
        set_.prompt = draft.prompt
        set_.post_date = (
            datetime.now(ZoneInfo("America/Los_Angeles")).date().isoformat()
        )
        set_.committed_at = datetime.now(UTC)
        set_.status = database.SetStatus.COMMITTED
        run = database.Run(
            external_run_id=external_run_id,
            set_id=set_id,
            draft_id=draft_id,
            type=database.RunType.BATCH,
            status=database.RunStatus.PENDING,
        )
        session.add(set_)
        session.add(run)
        session.commit()
        session.refresh(set_)

    return set_
