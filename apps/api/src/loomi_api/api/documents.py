from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, cast

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
)
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from loomi_api.api.dependencies import (
    CsrfOwnerContext,
    DbSession,
    OwnerContext,
    get_settings_from_app,
)
from loomi_api.db.models import Chunk, Document, DocumentTag, DocumentVersion, IngestionJob, Tag
from loomi_api.ingestion.errors import IngestionError
from loomi_api.ingestion.sanitize import sanitize_preview_text
from loomi_api.ingestion.service import (
    AcceptedUpload,
    RejectedUpload,
    accept_upload,
    count_document_chunks,
    count_document_embeddings,
    delete_document,
    process_ingestion_job,
    reindex_document,
    retry_document,
)

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


class DocumentSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    status: str
    source_kind: str
    created_at: datetime
    updated_at: datetime
    tag_names: list[str] = Field(default_factory=list)
    latest_job_id: str | None = None
    chunk_count: int = 0


class DocumentListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[DocumentSummary]
    total: int
    limit: int
    offset: int


class DocumentDetail(DocumentSummary):
    media_type: str | None = None
    checksum: str | None = None
    storage_size_bytes: int = 0
    parser_name: str | None = None
    parser_version: str | None = None
    embedding_count: int = 0
    source_metadata: dict[str, object] = Field(default_factory=dict)
    extraction_metadata: dict[str, object] = Field(default_factory=dict)
    latest_job: dict[str, object] | None = None


class UploadAcceptedItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_id: str
    document_version_id: str | None
    ingestion_job_id: str | None
    title: str
    status: str
    checksum: str
    media_type: str
    duplicate_of_document_id: str | None = None


class UploadRejectedItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    filename: str
    code: str
    detail: str


class UploadBatchResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    accepted: list[UploadAcceptedItem]
    rejected: list[UploadRejectedItem]


class PreviewChunk(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    ordinal: int
    safe_text: str
    provenance: dict[str, object]


class DocumentPreviewResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_id: str
    status: str
    chunks: list[PreviewChunk]


class JobActionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    ingestion_job_id: str
    status: str
    stage: str


class UpdateTagsRequest(BaseModel):
    tags: list[str] = Field(default_factory=list, max_length=20)


class TagsResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_id: str
    tags: list[str]


@router.post("/uploads", response_model=UploadBatchResponse, status_code=202)
async def upload_documents(
    request: Request,
    background_tasks: BackgroundTasks,
    session: DbSession,
    owner: CsrfOwnerContext,
    files: Annotated[list[UploadFile], File()],
    idempotency_key_form: Annotated[str | None, Form(alias="idempotency_key")] = None,
    idempotency_key_header: Annotated[str | None, Header(alias="idempotency-key")] = None,
) -> UploadBatchResponse:
    settings = get_settings_from_app(request)
    if len(files) > settings.max_upload_files:
        raise HTTPException(status_code=400, detail="Too many files in one upload request.")

    accepted: list[AcceptedUpload] = []
    rejected: list[RejectedUpload] = []
    base_key = idempotency_key_header or idempotency_key_form
    for index, upload in enumerate(files):
        try:
            accepted_item = await accept_upload(
                session=session,
                settings=settings,
                owner_user_id=owner.user.id,
                upload=upload,
                idempotency_key=f"{base_key}:{index}" if base_key else None,
                request_id=str(getattr(request.state, "request_id", "")),
                trace_id=str(getattr(request.state, "trace_id", "")),
            )
            accepted.append(accepted_item)
        except IngestionError as exc:
            rejected.append(
                RejectedUpload(
                    filename=upload.filename or "document",
                    code=exc.code,
                    detail=exc.detail,
                )
            )

    if not accepted and rejected:
        raise HTTPException(status_code=400, detail=rejected[0].detail)

    sessionmaker = cast(async_sessionmaker[AsyncSession], request.app.state.db_sessionmaker)
    for item in accepted:
        if item.ingestion_job_id is not None:
            background_tasks.add_task(
                process_ingestion_job,
                settings=settings,
                sessionmaker=sessionmaker,
                job_id=item.ingestion_job_id,
            )
    return UploadBatchResponse(
        accepted=[
            UploadAcceptedItem(
                document_id=item.document_id,
                document_version_id=item.document_version_id,
                ingestion_job_id=item.ingestion_job_id,
                title=item.title,
                status=item.status,
                checksum=item.checksum,
                media_type=item.media_type,
                duplicate_of_document_id=item.duplicate_of_document_id,
            )
            for item in accepted
        ],
        rejected=[
            UploadRejectedItem(filename=item.filename, code=item.code, detail=item.detail)
            for item in rejected
        ],
    )


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    session: DbSession,
    owner: OwnerContext,
    status: str | None = None,
    q: str | None = None,
    sort: Literal["created_desc", "created_asc", "title_asc", "updated_desc"] = "created_desc",
    limit: int = 25,
    offset: int = 0,
) -> DocumentListResponse:
    limit = min(max(limit, 1), 100)
    offset = max(offset, 0)
    filters = [Document.owner_user_id == owner.user.id, Document.deleted_at.is_(None)]
    if status:
        filters.append(Document.status == status)
    if q:
        filters.append(Document.title.ilike(f"%{q}%"))

    order_by: Any
    if sort == "created_asc":
        order_by = Document.created_at.asc()
    elif sort == "title_asc":
        order_by = Document.title.asc()
    elif sort == "updated_desc":
        order_by = Document.updated_at.desc()
    else:
        order_by = Document.created_at.desc()

    total = int(
        await session.scalar(select(func.count()).select_from(Document).where(*filters)) or 0
    )
    documents = list(
        await session.scalars(
            select(Document).where(*filters).order_by(order_by).limit(limit).offset(offset)
        )
    )
    return DocumentListResponse(
        items=[await _summary_for_document(session, document) for document in documents],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{document_id}", response_model=DocumentDetail)
async def get_document(
    document_id: str,
    session: DbSession,
    owner: OwnerContext,
) -> DocumentDetail:
    document = await _load_owner_document(session, owner.user.id, document_id)
    summary = await _summary_for_document(session, document)
    version = await _latest_version(session, document.id)
    latest_job = await _latest_job(session, document.id)
    return DocumentDetail(
        **summary.model_dump(),
        media_type=version.media_type if version else None,
        checksum=version.content_sha256 if version else None,
        storage_size_bytes=version.storage_size_bytes if version else 0,
        parser_name=version.parser_name if version else None,
        parser_version=version.parser_version if version else None,
        embedding_count=await count_document_embeddings(session, document.id),
        source_metadata=document.source_metadata,
        extraction_metadata=version.extraction_metadata if version else {},
        latest_job=_job_payload(latest_job) if latest_job else None,
    )


@router.get("/{document_id}/preview", response_model=DocumentPreviewResponse)
async def preview_document(
    document_id: str,
    session: DbSession,
    owner: OwnerContext,
    limit: int = 8,
) -> DocumentPreviewResponse:
    document = await _load_owner_document(session, owner.user.id, document_id)
    chunks = list(
        await session.scalars(
            select(Chunk)
            .where(Chunk.owner_user_id == owner.user.id, Chunk.document_id == document.id)
            .order_by(Chunk.ordinal.asc())
            .limit(min(max(limit, 1), 30))
        )
    )
    return DocumentPreviewResponse(
        document_id=document.id,
        status=document.status,
        chunks=[
            PreviewChunk(
                id=chunk.id,
                ordinal=chunk.ordinal,
                safe_text=sanitize_preview_text(chunk.text, limit=5000),
                provenance=chunk.provenance,
            )
            for chunk in chunks
        ],
    )


@router.post("/{document_id}/retry", response_model=JobActionResponse, status_code=202)
async def retry_ingestion(
    request: Request,
    background_tasks: BackgroundTasks,
    document_id: str,
    session: DbSession,
    owner: CsrfOwnerContext,
    idempotency_key: Annotated[str | None, Header(alias="idempotency-key")] = None,
) -> JobActionResponse:
    try:
        job = await retry_document(
            session=session,
            owner_user_id=owner.user.id,
            document_id=document_id,
            idempotency_key=idempotency_key,
            request_id=str(getattr(request.state, "request_id", "")),
            trace_id=str(getattr(request.state, "trace_id", "")),
        )
    except IngestionError as exc:
        _raise_http(exc)
    if job.status == "queued":
        _schedule_job(request, background_tasks, job.id)
    return JobActionResponse(ingestion_job_id=job.id, status=job.status, stage=job.stage)


@router.post("/{document_id}/reindex", response_model=JobActionResponse, status_code=202)
async def reindex(
    request: Request,
    background_tasks: BackgroundTasks,
    document_id: str,
    session: DbSession,
    owner: CsrfOwnerContext,
    idempotency_key: Annotated[str | None, Header(alias="idempotency-key")] = None,
) -> JobActionResponse:
    try:
        job = await reindex_document(
            session=session,
            owner_user_id=owner.user.id,
            document_id=document_id,
            idempotency_key=idempotency_key,
            request_id=str(getattr(request.state, "request_id", "")),
            trace_id=str(getattr(request.state, "trace_id", "")),
        )
    except IngestionError as exc:
        _raise_http(exc)
    if job.status == "queued":
        _schedule_job(request, background_tasks, job.id)
    return JobActionResponse(ingestion_job_id=job.id, status=job.status, stage=job.stage)


@router.delete("/{document_id}", status_code=204)
async def remove_document(
    request: Request,
    document_id: str,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> None:
    try:
        await delete_document(
            session=session,
            settings=get_settings_from_app(request),
            owner_user_id=owner.user.id,
            document_id=document_id,
            request_id=getattr(request.state, "request_id", None),
            trace_id=getattr(request.state, "trace_id", None),
        )
    except IngestionError as exc:
        _raise_http(exc)


@router.put("/{document_id}/tags", response_model=TagsResponse)
async def update_document_tags(
    document_id: str,
    payload: UpdateTagsRequest,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> TagsResponse:
    document = await _load_owner_document(session, owner.user.id, document_id)
    normalized = sorted({tag.strip().casefold() for tag in payload.tags if tag.strip()})
    await session.execute(delete(DocumentTag).where(DocumentTag.document_id == document.id))
    tag_names: list[str] = []
    for name in normalized[:20]:
        tag = await session.scalar(
            select(Tag).where(Tag.owner_user_id == owner.user.id, Tag.name == name)
        )
        if tag is None:
            tag = Tag(owner_user_id=owner.user.id, name=name)
            session.add(tag)
            await session.flush()
        session.add(DocumentTag(document_id=document.id, tag_id=tag.id))
        tag_names.append(tag.name)
    await session.commit()
    return TagsResponse(document_id=document.id, tags=tag_names)


def _schedule_job(request: Request, background_tasks: BackgroundTasks, job_id: str) -> None:
    settings = get_settings_from_app(request)
    sessionmaker = cast(async_sessionmaker[AsyncSession], request.app.state.db_sessionmaker)
    background_tasks.add_task(
        process_ingestion_job,
        settings=settings,
        sessionmaker=sessionmaker,
        job_id=job_id,
    )


async def _load_owner_document(
    session: AsyncSession, owner_user_id: str, document_id: str
) -> Document:
    document = await session.scalar(
        select(Document).where(
            Document.owner_user_id == owner_user_id,
            Document.id == document_id,
            Document.deleted_at.is_(None),
        )
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document


async def _summary_for_document(session: AsyncSession, document: Document) -> DocumentSummary:
    tag_names = list(
        await session.scalars(
            select(Tag.name)
            .join(DocumentTag, DocumentTag.tag_id == Tag.id)
            .where(DocumentTag.document_id == document.id)
            .order_by(Tag.name.asc())
        )
    )
    latest_job = await _latest_job(session, document.id)
    return DocumentSummary(
        id=document.id,
        title=document.title,
        status=document.status,
        source_kind=document.source_kind,
        created_at=document.created_at,
        updated_at=document.updated_at,
        tag_names=tag_names,
        latest_job_id=latest_job.id if latest_job else None,
        chunk_count=await count_document_chunks(session, document.id),
    )


async def _latest_version(session: AsyncSession, document_id: str) -> DocumentVersion | None:
    return cast(
        DocumentVersion | None,
        await session.scalar(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(desc(DocumentVersion.version_number))
            .limit(1)
        ),
    )


async def _latest_job(session: AsyncSession, document_id: str) -> IngestionJob | None:
    return cast(
        IngestionJob | None,
        await session.scalar(
            select(IngestionJob)
            .where(IngestionJob.document_id == document_id)
            .order_by(desc(IngestionJob.created_at))
            .limit(1)
        ),
    )


def _job_payload(job: IngestionJob) -> dict[str, object]:
    return {
        "id": job.id,
        "status": job.status,
        "stage": job.stage,
        "progress_percent": job.progress_percent,
        "error_code": job.error_code,
        "error_detail": job.error_detail,
        "stage_log": job.stage_log,
        "metrics": job.metrics,
    }


def _raise_http(exc: IngestionError) -> None:
    if exc.code.endswith("_not_found"):
        raise HTTPException(status_code=404, detail=exc.detail) from exc
    if exc.code in {"retry_not_allowed", "invalid_job_transition"}:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    raise HTTPException(status_code=400, detail=exc.detail) from exc
