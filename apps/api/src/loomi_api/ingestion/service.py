from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import cast
from uuid import UUID

import structlog
from fastapi import UploadFile
from sqlalchemy import delete, desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from loomi_api.config import Settings
from loomi_api.db.base import utc_now
from loomi_api.db.models import (
    AuditEvent,
    Chunk,
    Document,
    DocumentTag,
    DocumentVersion,
    Embedding,
    IngestionJob,
)
from loomi_api.ingestion.chunking import ChunkingConfig, DeterministicChunker
from loomi_api.ingestion.contracts import ChunkCandidate, EmbeddingVector, StoredObject
from loomi_api.ingestion.embeddings import DeterministicEmbeddingProvider
from loomi_api.ingestion.errors import IngestionError, UploadRejectedError
from loomi_api.ingestion.mime import detect_media_type
from loomi_api.ingestion.parsers import ParserRegistry
from loomi_api.ingestion.sanitize import safe_display_filename
from loomi_api.ingestion.scanner import ConfiguredMalwareScanner
from loomi_api.ingestion.state import (
    CANCELLED,
    CHUNKING,
    COMPLETED,
    EMBEDDING,
    EXTRACTING,
    FAILED,
    INDEXING,
    NORMALIZING,
    QUEUED,
    SCANNING,
    VALIDATING,
    progress_for_state,
    validate_transition,
)
from loomi_api.ingestion.storage import LocalObjectStore
from loomi_api.observability.telemetry import record_span

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class AcceptedUpload:
    document_id: str
    document_version_id: str | None
    ingestion_job_id: str | None
    title: str
    status: str
    checksum: str
    media_type: str
    duplicate_of_document_id: str | None = None


@dataclass(frozen=True)
class RejectedUpload:
    filename: str
    code: str
    detail: str


async def accept_upload(
    *,
    session: AsyncSession,
    settings: Settings,
    owner_user_id: str,
    upload: UploadFile,
    idempotency_key: str | None,
    request_id: str | None,
    trace_id: str | None,
) -> AcceptedUpload:
    display_filename = safe_display_filename(upload.filename)
    store = LocalObjectStore(settings.storage_root)
    temporary = await _write_upload_to_staging(upload, settings)
    try:
        media_type = detect_media_type(temporary.path, display_filename)
        duplicate = await _find_duplicate_document(
            session,
            owner_user_id=owner_user_id,
            checksum=temporary.sha256,
        )
        if duplicate is not None:
            store.path_for_key("staging/.keep").parent.mkdir(parents=True, exist_ok=True)
            temporary.path.unlink(missing_ok=True)
            document, version = duplicate
            return AcceptedUpload(
                document_id=document.id,
                document_version_id=version.id,
                ingestion_job_id=None,
                title=document.title,
                status=document.status,
                checksum=temporary.sha256,
                media_type=version.media_type or media_type,
                duplicate_of_document_id=document.id,
            )

        document = Document(
            owner_user_id=owner_user_id,
            title=display_filename,
            source_kind="upload",
            status=QUEUED,
            source_metadata={
                "display_filename": display_filename,
                "source_filename_normalized": True,
                "content_sha256": temporary.sha256,
                "size_bytes": temporary.size_bytes,
            },
        )
        session.add(document)
        await session.flush()

        version = DocumentVersion(
            document_id=document.id,
            version_number=1,
            object_key="pending",
            content_sha256=temporary.sha256,
            media_type=media_type,
            storage_size_bytes=temporary.size_bytes,
            extraction_metadata={
                "display_filename": display_filename,
                "media_type": media_type,
                "source_filename_normalized": True,
            },
        )
        session.add(version)
        await session.flush()

        object_key = store.reserve_key(owner_user_id, document.id, version.id)
        store.move_private_file(temporary.path, object_key)
        version.object_key = object_key

        job = IngestionJob(
            document_id=document.id,
            document_version_id=version.id,
            owner_user_id=owner_user_id,
            status=QUEUED,
            stage=QUEUED,
            idempotency_key=idempotency_key or f"upload:{temporary.sha256}",
            stage_log=[],
            metrics={
                "upload_size_bytes": temporary.size_bytes,
                "request_id": request_id,
                "trace_id": trace_id,
            },
        )
        session.add(job)
        await session.flush()
        await record_span(
            session,
            settings,
            name="loomi.ingestion.job_queued",
            component="ingestion",
            trace_id=trace_id,
            owner_user_id=owner_user_id,
            attributes={
                "document_id": document.id,
                "document_version_id": version.id,
                "job_id": job.id,
                "request_id": request_id,
                "trace_id": trace_id,
                "status": QUEUED,
                "stage": QUEUED,
            },
        )
        await session.commit()
        logger.info(
            "ingestion.upload_accepted",
            owner_user_id=owner_user_id,
            document_id=document.id,
            job_id=job.id,
            media_type=media_type,
            size_bytes=temporary.size_bytes,
        )
        return AcceptedUpload(
            document_id=document.id,
            document_version_id=version.id,
            ingestion_job_id=job.id,
            title=document.title,
            status=job.status,
            checksum=temporary.sha256,
            media_type=media_type,
        )
    except Exception:
        temporary.path.unlink(missing_ok=True)
        raise


async def process_ingestion_job(
    *,
    settings: Settings,
    sessionmaker: async_sessionmaker[AsyncSession],
    job_id: str,
) -> None:
    async with sessionmaker() as session:
        started = perf_counter()
        job, document, version = await _load_job_bundle(session, job_id)
        try:
            await _transition(session, job, document, VALIDATING, settings=settings)
            await _raise_if_cancelled(session, job, document, settings=settings)

            store = LocalObjectStore(settings.storage_root)
            object_path = store.path_for_key(version.object_key)
            if not object_path.exists():
                raise IngestionError("source_missing", "The stored source object is missing.")

            await _transition(session, job, document, SCANNING, settings=settings)
            await ConfiguredMalwareScanner(settings).scan(object_path)
            await _raise_if_cancelled(session, job, document, settings=settings)

            await _transition(session, job, document, EXTRACTING, settings=settings)
            parsed = await ParserRegistry(settings).parse(
                object_path,
                version.media_type or "application/octet-stream",
                str(version.extraction_metadata.get("display_filename", document.title)),
            )
            await _raise_if_cancelled(session, job, document, settings=settings)

            await _transition(session, job, document, NORMALIZING, settings=settings)
            version.parser_name = parsed.parser_name
            version.parser_version = parsed.parser_version
            version.extraction_metadata = {
                **version.extraction_metadata,
                "parser": parsed.parser_name,
                "parser_version": parsed.parser_version,
                "warnings": list(parsed.warnings),
                "metadata": parsed.metadata,
                "ingested_at": utc_now().isoformat(),
            }

            await _transition(session, job, document, CHUNKING, settings=settings)
            chunks = DeterministicChunker(
                ChunkingConfig(
                    target_chars=settings.chunk_target_chars,
                    overlap_chars=settings.chunk_overlap_chars,
                    max_chunks=settings.max_chunks_per_document,
                )
            ).chunk(
                owner_user_id=document.owner_user_id,
                document_id=document.id,
                version_id=version.id,
                source_checksum=version.content_sha256,
                parsed=parsed,
            )
            await _raise_if_cancelled(session, job, document, settings=settings)

            await _transition(session, job, document, EMBEDDING, settings=settings)
            vectors = await DeterministicEmbeddingProvider(
                model=settings.embedding_model,
                dimensions=settings.embedding_dimensions,
            ).embed([chunk.text for chunk in chunks])
            await _raise_if_cancelled(session, job, document, settings=settings)

            await _transition(session, job, document, INDEXING, settings=settings)
            await _replace_indexes(session, document, version, chunks, vectors)
            elapsed_ms = round((perf_counter() - started) * 1000)
            job.metrics = {
                **job.metrics,
                "chunk_count": len(chunks),
                "embedding_count": len(vectors),
                "parser": parsed.parser_name,
                "embedding_model": settings.embedding_model,
                "elapsed_ms": elapsed_ms,
            }
            await _transition(session, job, document, COMPLETED, settings=settings)
            logger.info(
                "ingestion.completed",
                owner_user_id=document.owner_user_id,
                document_id=document.id,
                job_id=job.id,
                chunk_count=len(chunks),
                embedding_count=len(vectors),
                elapsed_ms=elapsed_ms,
            )
        except IngestionError as exc:
            if exc.code == "ingestion_cancelled":
                logger.info(
                    "ingestion.cancelled",
                    owner_user_id=document.owner_user_id,
                    document_id=document.id,
                    job_id=job.id,
                )
                return
            await _fail_job(session, settings, job, document, exc.code, exc.detail)
        except Exception:  # pragma: no cover - defensive safe error boundary
            logger.exception("ingestion.unhandled_failure", job_id=job.id, document_id=document.id)
            await _fail_job(
                session,
                settings,
                job,
                document,
                "ingestion_failed",
                "The document could not be ingested safely.",
            )


async def retry_document(
    *,
    session: AsyncSession,
    owner_user_id: str,
    document_id: str,
    idempotency_key: str | None,
    request_id: str | None,
    trace_id: str | None,
) -> IngestionJob:
    document, version = await _load_owner_document_and_latest_version(
        session,
        owner_user_id=owner_user_id,
        document_id=document_id,
    )
    last_job = await session.scalar(
        select(IngestionJob)
        .where(
            IngestionJob.owner_user_id == owner_user_id,
            IngestionJob.document_id == document_id,
        )
        .order_by(desc(IngestionJob.created_at))
        .limit(1)
    )
    if last_job is not None and last_job.status not in {FAILED, CANCELLED}:
        raise IngestionError(
            "retry_not_allowed", "Only failed or cancelled ingestions can be retried."
        )
    return await _create_followup_job(
        session,
        document=document,
        version=version,
        idempotency_key=idempotency_key,
        reason="retry",
        request_id=request_id,
        trace_id=trace_id,
    )


async def reindex_document(
    *,
    session: AsyncSession,
    owner_user_id: str,
    document_id: str,
    idempotency_key: str | None,
    request_id: str | None,
    trace_id: str | None,
) -> IngestionJob:
    document, version = await _load_owner_document_and_latest_version(
        session,
        owner_user_id=owner_user_id,
        document_id=document_id,
    )
    return await _create_followup_job(
        session,
        document=document,
        version=version,
        idempotency_key=idempotency_key,
        reason="reindex",
        request_id=request_id,
        trace_id=trace_id,
    )


async def cancel_job(*, session: AsyncSession, owner_user_id: str, job_id: str) -> IngestionJob:
    row = await session.execute(
        select(IngestionJob, Document)
        .join(Document, IngestionJob.document_id == Document.id)
        .where(
            IngestionJob.owner_user_id == owner_user_id,
            IngestionJob.id == job_id,
        )
    )
    result = row.one_or_none()
    if result is None:
        raise IngestionError("job_not_found", "Ingestion job not found.")
    job, document = result
    if job.status in {COMPLETED, FAILED, CANCELLED}:
        return cast(IngestionJob, job)
    job.cancel_requested_at = utc_now()
    job.status = CANCELLED
    job.stage = CANCELLED
    job.progress_percent = 100
    job.completed_at = utc_now()
    job.stage_log = [*job.stage_log, _stage_log_entry(CANCELLED)]
    document.status = CANCELLED
    await session.commit()
    return cast(IngestionJob, job)


async def delete_document(
    *,
    session: AsyncSession,
    settings: Settings,
    owner_user_id: str,
    document_id: str,
    request_id: str | None,
    trace_id: str | None,
) -> None:
    document = await session.scalar(
        select(Document).where(
            Document.owner_user_id == owner_user_id,
            Document.id == document_id,
            Document.deleted_at.is_(None),
        )
    )
    if document is None:
        raise IngestionError("document_not_found", "Document not found.")
    versions = list(
        await session.scalars(
            select(DocumentVersion).where(DocumentVersion.document_id == document.id)
        )
    )
    store = LocalObjectStore(settings.storage_root)
    for version in versions:
        store.delete(version.object_key)

    chunk_ids = list(
        await session.scalars(select(Chunk.id).where(Chunk.document_id == document.id))
    )
    if chunk_ids:
        await session.execute(delete(Embedding).where(Embedding.chunk_id.in_(chunk_ids)))
    await session.execute(delete(Chunk).where(Chunk.document_id == document.id))
    await session.execute(delete(IngestionJob).where(IngestionJob.document_id == document.id))
    await session.execute(delete(DocumentVersion).where(DocumentVersion.document_id == document.id))
    await session.execute(delete(DocumentTag).where(DocumentTag.document_id == document.id))
    await session.delete(document)
    session.add(
        AuditEvent(
            owner_user_id=owner_user_id,
            event_type="document.deleted",
            request_id=request_id,
            trace_id=trace_id,
            event_metadata={"document_id": document_id},
        )
    )
    await session.commit()


async def count_document_chunks(session: AsyncSession, document_id: str) -> int:
    return int(
        await session.scalar(
            select(func.count()).select_from(Chunk).where(Chunk.document_id == document_id)
        )
        or 0
    )


async def count_document_embeddings(session: AsyncSession, document_id: str) -> int:
    chunk_ids = select(Chunk.id).where(Chunk.document_id == document_id)
    return int(
        await session.scalar(
            select(func.count()).select_from(Embedding).where(Embedding.chunk_id.in_(chunk_ids))
        )
        or 0
    )


async def _write_upload_to_staging(upload: UploadFile, settings: Settings) -> StoredObject:
    staging = settings.storage_root / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    key = f"staging/{secrets.token_urlsafe(24)}.upload"
    path = staging / Path(key).name
    hasher = hashlib.sha256()
    size = 0
    try:
        with path.open("wb") as handle:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise UploadRejectedError(
                        "upload_too_large",
                        "The uploaded file exceeds the configured size limit.",
                    )
                hasher.update(chunk)
                handle.write(chunk)
    finally:
        await upload.close()
    if size == 0:
        path.unlink(missing_ok=True)
        raise UploadRejectedError("empty_upload", "Empty files are not supported.")
    return StoredObject(key=key, path=path, size_bytes=size, sha256=hasher.hexdigest())


async def _find_duplicate_document(
    session: AsyncSession,
    *,
    owner_user_id: str,
    checksum: str,
) -> tuple[Document, DocumentVersion] | None:
    row = await session.execute(
        select(Document, DocumentVersion)
        .join(DocumentVersion, DocumentVersion.document_id == Document.id)
        .where(
            Document.owner_user_id == owner_user_id,
            Document.deleted_at.is_(None),
            DocumentVersion.content_sha256 == checksum,
        )
        .order_by(desc(Document.created_at))
        .limit(1)
    )
    result = row.one_or_none()
    if result is None:
        return None
    document, version = result._tuple()
    return document, version


async def _load_job_bundle(
    session: AsyncSession, job_id: str
) -> tuple[IngestionJob, Document, DocumentVersion]:
    row = await session.execute(
        select(IngestionJob, Document, DocumentVersion)
        .join(Document, IngestionJob.document_id == Document.id)
        .join(DocumentVersion, IngestionJob.document_version_id == DocumentVersion.id)
        .where(IngestionJob.id == job_id)
    )
    result = row.one_or_none()
    if result is None:
        raise IngestionError("job_not_found", "Ingestion job not found.")
    job, document, version = result._tuple()
    return job, document, version


async def _load_owner_document_and_latest_version(
    session: AsyncSession,
    *,
    owner_user_id: str,
    document_id: str,
) -> tuple[Document, DocumentVersion]:
    row = await session.execute(
        select(Document, DocumentVersion)
        .join(DocumentVersion, DocumentVersion.document_id == Document.id)
        .where(
            Document.owner_user_id == owner_user_id,
            Document.id == document_id,
            Document.deleted_at.is_(None),
        )
        .order_by(desc(DocumentVersion.version_number))
        .limit(1)
    )
    result = row.one_or_none()
    if result is None:
        raise IngestionError("document_not_found", "Document not found.")
    document, version = result._tuple()
    return document, version


async def _create_followup_job(
    session: AsyncSession,
    *,
    document: Document,
    version: DocumentVersion,
    idempotency_key: str | None,
    reason: str,
    request_id: str | None,
    trace_id: str | None,
) -> IngestionJob:
    if idempotency_key:
        existing = await session.scalar(
            select(IngestionJob)
            .where(
                IngestionJob.owner_user_id == document.owner_user_id,
                IngestionJob.document_id == document.id,
                IngestionJob.idempotency_key == idempotency_key,
            )
            .order_by(desc(IngestionJob.created_at))
            .limit(1)
        )
        if existing is not None:
            return existing
    job = IngestionJob(
        document_id=document.id,
        document_version_id=version.id,
        owner_user_id=document.owner_user_id,
        status=QUEUED,
        stage=QUEUED,
        idempotency_key=idempotency_key or f"{reason}:{document.id}:{secrets.token_urlsafe(12)}",
        stage_log=[],
        metrics={"reason": reason, "request_id": request_id, "trace_id": trace_id},
    )
    document.status = QUEUED
    session.add(job)
    await session.commit()
    return job


async def _transition(
    session: AsyncSession,
    job: IngestionJob,
    document: Document,
    target: str,
    *,
    settings: Settings | None = None,
) -> None:
    validate_transition(job.status, target)
    now = utc_now()
    if job.started_at is None:
        job.started_at = now
    job.status = target
    job.stage = target
    job.progress_percent = progress_for_state(target)
    if target in {COMPLETED, FAILED, CANCELLED}:
        job.completed_at = now
    job.stage_log = [*job.stage_log, _stage_log_entry(target)]
    document.status = target
    if settings is not None:
        metrics = job.metrics or {}
        await record_span(
            session,
            settings,
            name="loomi.ingestion.stage",
            component="ingestion",
            trace_id=str(metrics.get("trace_id") or job.id),
            owner_user_id=job.owner_user_id,
            status="error" if target == FAILED else "ok",
            error_code=job.error_code if target == FAILED else None,
            attributes={
                "document_id": document.id,
                "document_version_id": job.document_version_id,
                "job_id": job.id,
                "request_id": metrics.get("request_id"),
                "trace_id": metrics.get("trace_id") or job.id,
                "stage": target,
                "status": target,
            },
        )
    await session.commit()


async def _raise_if_cancelled(
    session: AsyncSession,
    job: IngestionJob,
    document: Document,
    *,
    settings: Settings | None = None,
) -> None:
    await session.refresh(job)
    if job.status == CANCELLED:
        document.status = CANCELLED
        await session.commit()
        raise IngestionError("ingestion_cancelled", "Ingestion was cancelled.")
    if job.cancel_requested_at is not None:
        await _transition(session, job, document, CANCELLED, settings=settings)
        raise IngestionError("ingestion_cancelled", "Ingestion was cancelled.")


async def _replace_indexes(
    session: AsyncSession,
    document: Document,
    version: DocumentVersion,
    chunks: list[ChunkCandidate],
    vectors: list[EmbeddingVector],
) -> None:
    existing_chunk_ids = list(
        await session.scalars(select(Chunk.id).where(Chunk.document_version_id == version.id))
    )
    if existing_chunk_ids:
        await session.execute(delete(Embedding).where(Embedding.chunk_id.in_(existing_chunk_ids)))
    await session.execute(delete(Chunk).where(Chunk.document_version_id == version.id))

    for chunk, vector in zip(chunks, vectors, strict=True):
        chunk_id = _uuid_from_sha256(chunk.stable_id)
        session.add(
            Chunk(
                id=chunk_id,
                document_id=document.id,
                document_version_id=version.id,
                owner_user_id=document.owner_user_id,
                ordinal=chunk.ordinal,
                stable_id=chunk.stable_id,
                text=chunk.text,
                text_sha256=chunk.text_sha256,
                token_count=chunk.token_count,
                chunker_version=str(chunk.provenance["chunker"]),
                provenance={
                    **chunk.provenance,
                    "owner_user_id": document.owner_user_id,
                    "document_id": document.id,
                    "document_version_id": version.id,
                    "checksum": version.content_sha256,
                    "media_type": version.media_type,
                },
            )
        )
        session.add(
            embedding := Embedding(
                chunk_id=chunk_id,
                owner_user_id=document.owner_user_id,
                provider=vector.provider,
                model=vector.model,
                dimensions=vector.dimensions,
                embedding_version=vector.version,
                vector_checksum=vector.checksum,
                vector_json=vector.vector,
            )
        )
        await session.flush()
        await _store_pgvector(session, embedding.id, vector.vector)
    await session.commit()


async def _fail_job(
    session: AsyncSession,
    settings: Settings,
    job: IngestionJob,
    document: Document,
    code: str,
    detail: str,
) -> None:
    job.error_code = code
    job.error_detail = detail
    if job.status != FAILED:
        await _transition(session, job, document, FAILED, settings=settings)
    else:
        await session.commit()
    logger.info(
        "ingestion.failed",
        owner_user_id=document.owner_user_id,
        document_id=document.id,
        job_id=job.id,
        error_code=code,
    )


def _stage_log_entry(stage: str) -> dict[str, str]:
    return {"stage": stage, "at": utc_now().isoformat()}


def _uuid_from_sha256(value: str) -> str:
    return str(UUID(value[:32]))


async def _store_pgvector(session: AsyncSession, embedding_id: str, vector: list[float]) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    vector_literal = "[" + ",".join(f"{value:.8f}" for value in vector) + "]"
    await session.execute(
        text("update embeddings set vector = CAST(:vector AS vector) where id = :embedding_id"),
        {"vector": vector_literal, "embedding_id": embedding_id},
    )
