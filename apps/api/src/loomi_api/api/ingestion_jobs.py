from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from loomi_api.api.dependencies import CsrfOwnerContext, DbSession, OwnerContext
from loomi_api.db.models import IngestionJob
from loomi_api.ingestion.errors import IngestionError
from loomi_api.ingestion.service import cancel_job

router = APIRouter(prefix="/api/v1/ingestion-jobs", tags=["ingestion-jobs"])


class IngestionJobDetail(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    document_id: str
    document_version_id: str | None
    status: str
    stage: str
    progress_percent: int
    attempts: int
    error_code: str | None
    error_detail: str | None
    stage_log: list[dict[str, object]] = Field(default_factory=list)
    metrics: dict[str, object] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    cancel_requested_at: datetime | None


@router.get("/{job_id}", response_model=IngestionJobDetail)
async def get_ingestion_job(
    job_id: str,
    session: DbSession,
    owner: OwnerContext,
) -> IngestionJobDetail:
    job = await session.scalar(
        select(IngestionJob).where(
            IngestionJob.owner_user_id == owner.user.id,
            IngestionJob.id == job_id,
        )
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Ingestion job not found.")
    return _job_detail(job)


@router.post("/{job_id}/cancel", response_model=IngestionJobDetail)
async def cancel_ingestion_job(
    job_id: str,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> IngestionJobDetail:
    try:
        job = await cancel_job(session=session, owner_user_id=owner.user.id, job_id=job_id)
    except IngestionError as exc:
        raise HTTPException(status_code=404, detail=exc.detail) from exc
    return _job_detail(job)


def _job_detail(job: IngestionJob) -> IngestionJobDetail:
    return IngestionJobDetail(
        id=job.id,
        document_id=job.document_id,
        document_version_id=job.document_version_id,
        status=job.status,
        stage=job.stage,
        progress_percent=job.progress_percent,
        attempts=job.attempts,
        error_code=job.error_code,
        error_detail=job.error_detail,
        stage_log=job.stage_log,
        metrics=job.metrics,
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        cancel_requested_at=job.cancel_requested_at,
    )
