from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from loomi_api.api.dependencies import DbSession, OwnerContext
from loomi_api.db.models import Document

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


class DocumentSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    status: str
    created_at: datetime
    updated_at: datetime


@router.get("", response_model=list[DocumentSummary])
async def list_documents(
    session: DbSession,
    owner: OwnerContext,
) -> list[DocumentSummary]:
    result = await session.scalars(
        select(Document)
        .where(Document.owner_user_id == owner.user.id, Document.deleted_at.is_(None))
        .order_by(Document.created_at.desc())
    )
    return [
        DocumentSummary(
            id=document.id,
            title=document.title,
            status=document.status,
            created_at=document.created_at,
            updated_at=document.updated_at,
        )
        for document in result
    ]
