from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import Select, and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from loomi_api.config import Settings
from loomi_api.db.models import (
    Chunk,
    CollectionDocument,
    Document,
    DocumentTag,
    DocumentVersion,
    Embedding,
    Tag,
)
from loomi_api.ingestion.embeddings import DeterministicEmbeddingProvider
from loomi_api.retrieval.contracts import (
    ContextItem,
    RetrievalQuery,
    RetrievalResult,
    RetrievedCandidate,
    SearchFilters,
)
from loomi_api.retrieval.scoring import (
    lexical_score,
    normalized_cosine_score,
    reciprocal_rank_fusion,
    token_jaccard,
)


class RetrievalError(ValueError):
    """Raised for invalid retrieval requests."""


@dataclass(frozen=True)
class RetrievalConfig:
    candidate_limit: int = 48
    context_max_chunks: int = 6
    context_token_budget: int = 1800
    max_chunks_per_document: int = 3
    near_duplicate_threshold: float = 0.92
    rrf_k: int = 60


@dataclass(frozen=True)
class _ChunkRecord:
    chunk: Chunk
    document: Document
    version: DocumentVersion
    embedding: Embedding | None
    tag_names: tuple[str, ...]


class LexicalRetriever:
    def __init__(self, config: RetrievalConfig | None = None) -> None:
        self.config = config or RetrievalConfig()

    async def retrieve(
        self,
        session: AsyncSession,
        query: RetrievalQuery,
    ) -> tuple[RetrievedCandidate, ...]:
        validate_query(query)
        if _dialect_name(session) == "postgresql":
            pg_candidates = await _postgres_lexical(session, query, self.config)
            if pg_candidates:
                return pg_candidates
        records = await _load_chunk_records(session, query.owner_user_id, query.filters)
        candidates: list[RetrievedCandidate] = []
        for record in records:
            score, debug = lexical_score(
                query.query,
                record.chunk.text,
                title=record.document.title,
            )
            if score <= 0:
                continue
            candidates.append(
                _candidate_from_record(
                    record,
                    score=score,
                    lexical_score=score,
                    semantic_score=None,
                    debug={"lexical": debug},
                )
            )
        return _rank(candidates, limit=self.config.candidate_limit)


class VectorRetriever:
    def __init__(self, settings: Settings, config: RetrievalConfig | None = None) -> None:
        self.settings = settings
        self.config = config or RetrievalConfig()

    async def retrieve(
        self,
        session: AsyncSession,
        query: RetrievalQuery,
    ) -> tuple[RetrievedCandidate, ...]:
        validate_query(query)
        query_vector = (
            await DeterministicEmbeddingProvider(
                model=self.settings.embedding_model,
                dimensions=self.settings.embedding_dimensions,
            ).embed([query.query])
        )[0].vector
        if _dialect_name(session) == "postgresql":
            pg_candidates = await _postgres_vector(session, query, self.config, query_vector)
            if pg_candidates:
                return pg_candidates
        records = await _load_chunk_records(session, query.owner_user_id, query.filters)
        candidates: list[RetrievedCandidate] = []
        for record in records:
            if record.embedding is None:
                continue
            semantic = normalized_cosine_score(
                _as_float_list(record.embedding.vector_json),
                query_vector,
            )
            overlap_score, overlap_debug = lexical_score(
                query.query,
                record.chunk.text,
                title=record.document.title,
            )
            score = min((semantic * 0.74) + (overlap_score * 0.26), 1.0)
            candidates.append(
                _candidate_from_record(
                    record,
                    score=score,
                    lexical_score=overlap_score,
                    semantic_score=semantic,
                    debug={"semantic": round(semantic, 4), "lexical_tie_breaker": overlap_debug},
                )
            )
        return _rank(candidates, limit=self.config.candidate_limit)


class HybridRetriever:
    def __init__(
        self,
        lexical: LexicalRetriever,
        vector: VectorRetriever,
        config: RetrievalConfig | None = None,
    ) -> None:
        self.lexical = lexical
        self.vector = vector
        self.config = config or RetrievalConfig()

    async def retrieve(
        self,
        session: AsyncSession,
        query: RetrievalQuery,
    ) -> tuple[RetrievedCandidate, ...]:
        validate_query(query)
        lexical_candidates = await self.lexical.retrieve(session, query)
        vector_candidates = await self.vector.retrieve(session, query)
        by_chunk: dict[str, RetrievedCandidate] = {
            candidate.chunk_id: candidate for candidate in vector_candidates
        }
        by_chunk.update({candidate.chunk_id: candidate for candidate in lexical_candidates})
        fused = reciprocal_rank_fusion(
            (
                (1.0, [candidate.chunk_id for candidate in lexical_candidates]),
                (0.85, [candidate.chunk_id for candidate in vector_candidates]),
            ),
            k=self.config.rrf_k,
        )
        candidates: list[RetrievedCandidate] = []
        lexical_scores = {
            candidate.chunk_id: candidate.lexical_score for candidate in lexical_candidates
        }
        semantic_scores = {
            candidate.chunk_id: candidate.semantic_score for candidate in vector_candidates
        }
        for chunk_id, score in fused.items():
            candidate = by_chunk[chunk_id]
            candidates.append(
                _replace_candidate_score(
                    candidate,
                    score=score,
                    lexical_score=lexical_scores.get(chunk_id),
                    semantic_score=semantic_scores.get(chunk_id),
                    debug={
                        **candidate.debug,
                        "fusion": {
                            "method": "reciprocal_rank_fusion",
                            "k": self.config.rrf_k,
                            "lexical_weight": 1.0,
                            "semantic_weight": 0.85,
                        },
                    },
                )
            )
        return _rank(candidates, limit=self.config.candidate_limit)


class NullReranker:
    async def rerank(
        self,
        query: str,
        candidates: tuple[RetrievedCandidate, ...],
    ) -> tuple[RetrievedCandidate, ...]:
        return candidates


class TokenBudgetContextAssembler:
    def __init__(self, config: RetrievalConfig | None = None) -> None:
        self.config = config or RetrievalConfig()

    def assemble(
        self,
        *,
        query: RetrievalQuery,
        candidates: tuple[RetrievedCandidate, ...],
    ) -> tuple[ContextItem, ...]:
        selected: list[ContextItem] = []
        used_tokens = 0
        seen_hashes: set[str] = set()
        per_document: dict[str, int] = {}
        for candidate in candidates:
            if candidate.score < query.min_score:
                continue
            if candidate.text_sha256 in seen_hashes:
                continue
            if per_document.get(candidate.document_id, 0) >= self.config.max_chunks_per_document:
                continue
            if any(
                token_jaccard(candidate.text, existing.candidate.text)
                >= self.config.near_duplicate_threshold
                for existing in selected
            ):
                continue
            next_token_count = max(candidate.token_count, 1)
            if selected and used_tokens + next_token_count > self.config.context_token_budget:
                break
            if next_token_count > self.config.context_token_budget:
                continue
            allowed_id = f"ctx_{len(selected) + 1}"
            selected.append(
                ContextItem(
                    allowed_citation_id=allowed_id,
                    candidate=candidate,
                    excerpt=_excerpt(candidate.text),
                )
            )
            seen_hashes.add(candidate.text_sha256)
            per_document[candidate.document_id] = per_document.get(candidate.document_id, 0) + 1
            used_tokens += next_token_count
            if len(selected) >= self.config.context_max_chunks:
                break
        return tuple(selected)


class RetrievalService:
    def __init__(self, settings: Settings, config: RetrievalConfig | None = None) -> None:
        self.config = config or RetrievalConfig()
        self.lexical = LexicalRetriever(self.config)
        self.vector = VectorRetriever(settings, self.config)
        self.hybrid = HybridRetriever(self.lexical, self.vector, self.config)
        self.reranker = NullReranker()
        self.context_assembler = TokenBudgetContextAssembler(self.config)

    async def search(
        self,
        session: AsyncSession,
        query: RetrievalQuery,
    ) -> RetrievalResult:
        if query.mode == "lexical":
            candidates = await self.lexical.retrieve(session, query)
        elif query.mode == "semantic":
            candidates = await self.vector.retrieve(session, query)
        else:
            candidates = await self.hybrid.retrieve(session, query)
        candidates = await self.reranker.rerank(query.query, candidates)
        filtered = tuple(
            candidate for candidate in candidates if candidate.score >= query.min_score
        )
        paged = filtered[query.offset : query.offset + query.limit]
        context = self.context_assembler.assemble(query=query, candidates=filtered)
        warnings: list[str] = []
        if not filtered:
            warnings.append("No chunks met the relevance threshold.")
        return RetrievalResult(
            mode=query.mode,
            query=query.query,
            candidates=paged,
            selected_context=context,
            total=len(filtered),
            warnings=tuple(warnings),
            debug={
                "vector_metric": "cosine",
                "rank_fusion": "reciprocal_rank_fusion" if query.mode == "hybrid" else None,
                "candidate_limit": self.config.candidate_limit,
            },
        )


def validate_query(query: RetrievalQuery) -> None:
    stripped = query.query.strip()
    if len(stripped) < 2:
        raise RetrievalError("Search query must be at least 2 characters.")
    if len(stripped) > 500:
        raise RetrievalError("Search query must be at most 500 characters.")
    if query.limit < 1 or query.limit > 50:
        raise RetrievalError("Search limit must be between 1 and 50.")
    if query.offset < 0:
        raise RetrievalError("Search offset must be non-negative.")
    if query.min_score < 0 or query.min_score > 1:
        raise RetrievalError("Minimum score must be between 0 and 1.")


async def _load_chunk_records(
    session: AsyncSession,
    owner_user_id: str,
    filters: SearchFilters,
) -> list[_ChunkRecord]:
    stmt = (
        select(Chunk, Document, DocumentVersion, Embedding)
        .join(Document, Chunk.document_id == Document.id)
        .join(DocumentVersion, Chunk.document_version_id == DocumentVersion.id)
        .outerjoin(Embedding, Embedding.chunk_id == Chunk.id)
        .where(
            Document.owner_user_id == owner_user_id,
            Chunk.owner_user_id == owner_user_id,
            Document.deleted_at.is_(None),
            Document.status == "completed",
        )
        .order_by(Document.created_at.desc(), Chunk.ordinal.asc())
    )
    stmt = _apply_filters(stmt, filters)
    rows = list((await session.execute(stmt)).all())
    tag_names = await _tag_names_by_document(
        session,
        owner_user_id,
        tuple({cast(Document, row[1]).id for row in rows}),
    )
    return [
        _ChunkRecord(
            chunk=cast(Chunk, row[0]),
            document=cast(Document, row[1]),
            version=cast(DocumentVersion, row[2]),
            embedding=cast(Embedding | None, row[3]),
            tag_names=tag_names.get(cast(Document, row[1]).id, ()),
        )
        for row in rows
    ]


def _apply_filters(
    stmt: Select[Any],
    filters: SearchFilters,
) -> Select[Any]:
    clauses: list[Any] = []
    if filters.document_ids:
        clauses.append(Document.id.in_(filters.document_ids))
    if filters.source_types:
        clauses.append(Document.source_kind.in_(filters.source_types))
    if filters.created_from is not None:
        clauses.append(Document.created_at >= filters.created_from)
    if filters.created_to is not None:
        clauses.append(Document.created_at <= filters.created_to)
    if filters.tags:
        clauses.append(
            Document.id.in_(
                select(DocumentTag.document_id)
                .join(Tag, Tag.id == DocumentTag.tag_id)
                .where(Tag.name.in_(tuple(tag.casefold() for tag in filters.tags)))
            )
        )
    if filters.collection_ids:
        clauses.append(
            Document.id.in_(
                select(CollectionDocument.document_id).where(
                    CollectionDocument.collection_id.in_(filters.collection_ids)
                )
            )
        )
    if clauses:
        stmt = stmt.where(and_(*clauses))
    return stmt


async def _tag_names_by_document(
    session: AsyncSession,
    owner_user_id: str,
    document_ids: tuple[str, ...],
) -> dict[str, tuple[str, ...]]:
    if not document_ids:
        return {}
    rows = list(
        (
            await session.execute(
                select(DocumentTag.document_id, Tag.name)
                .join(Tag, Tag.id == DocumentTag.tag_id)
                .where(
                    Tag.owner_user_id == owner_user_id, DocumentTag.document_id.in_(document_ids)
                )
                .order_by(Tag.name.asc())
            )
        ).all()
    )
    output: dict[str, list[str]] = {}
    for document_id, tag_name in rows:
        output.setdefault(str(document_id), []).append(str(tag_name))
    return {document_id: tuple(names) for document_id, names in output.items()}


async def _postgres_lexical(
    session: AsyncSession,
    query: RetrievalQuery,
    config: RetrievalConfig,
) -> tuple[RetrievedCandidate, ...]:
    records = await _load_chunk_records(session, query.owner_user_id, query.filters)
    if not records:
        return ()
    # PostgreSQL FTS is used to order candidate IDs; full metadata is assembled
    # through the same owner-scoped loader to keep authorization in one place.
    params = {
        "owner_user_id": query.owner_user_id,
        "query": query.query,
        "limit": config.candidate_limit,
    }
    rows = list(
        (
            await session.execute(
                text(
                    """
                    select c.id as chunk_id,
                           ts_rank_cd(
                             to_tsvector('english', c.text),
                             plainto_tsquery('english', :query)
                           ) as rank
                    from chunks c
                    join documents d on d.id = c.document_id
                    where d.owner_user_id = :owner_user_id
                      and c.owner_user_id = :owner_user_id
                      and d.deleted_at is null
                      and d.status = 'completed'
                      and to_tsvector('english', c.text) @@ plainto_tsquery('english', :query)
                    order by rank desc
                    limit :limit
                    """
                ),
                params,
            )
        ).mappings()
    )
    rank_by_id = {str(row["chunk_id"]): float(row["rank"] or 0.0) for row in rows}
    if not rank_by_id:
        return ()
    max_rank = max(rank_by_id.values()) or 1.0
    by_id = {record.chunk.id: record for record in records}
    candidates = [
        _candidate_from_record(
            by_id[chunk_id],
            score=min(rank / max_rank, 1.0),
            lexical_score=min(rank / max_rank, 1.0),
            semantic_score=None,
            debug={"postgres_fts_rank": rank},
        )
        for chunk_id, rank in rank_by_id.items()
        if chunk_id in by_id
    ]
    return _rank(candidates, limit=config.candidate_limit)


async def _postgres_vector(
    session: AsyncSession,
    query: RetrievalQuery,
    config: RetrievalConfig,
    query_vector: list[float],
) -> tuple[RetrievedCandidate, ...]:
    records = await _load_chunk_records(session, query.owner_user_id, query.filters)
    if not records:
        return ()
    vector_literal = "[" + ",".join(f"{value:.8f}" for value in query_vector) + "]"
    rows = list(
        (
            await session.execute(
                text(
                    """
                    select c.id as chunk_id,
                           1 - (e.vector <=> CAST(:query_vector AS vector)) as similarity
                    from embeddings e
                    join chunks c on c.id = e.chunk_id
                    join documents d on d.id = c.document_id
                    where d.owner_user_id = :owner_user_id
                      and e.owner_user_id = :owner_user_id
                      and c.owner_user_id = :owner_user_id
                      and d.deleted_at is null
                      and d.status = 'completed'
                      and e.vector is not null
                    order by e.vector <=> CAST(:query_vector AS vector)
                    limit :limit
                    """
                ),
                {
                    "owner_user_id": query.owner_user_id,
                    "query_vector": vector_literal,
                    "limit": config.candidate_limit,
                },
            )
        ).mappings()
    )
    similarity_by_id = {str(row["chunk_id"]): float(row["similarity"] or 0.0) for row in rows}
    if not similarity_by_id:
        return ()
    by_id = {record.chunk.id: record for record in records}
    candidates = [
        _candidate_from_record(
            by_id[chunk_id],
            score=max(0.0, min(similarity, 1.0)),
            lexical_score=None,
            semantic_score=max(0.0, min(similarity, 1.0)),
            debug={"pgvector_metric": "cosine", "pgvector_similarity": round(similarity, 4)},
        )
        for chunk_id, similarity in similarity_by_id.items()
        if chunk_id in by_id
    ]
    return _rank(candidates, limit=config.candidate_limit)


def _candidate_from_record(
    record: _ChunkRecord,
    *,
    score: float,
    lexical_score: float | None,
    semantic_score: float | None,
    debug: dict[str, object],
) -> RetrievedCandidate:
    return RetrievedCandidate(
        chunk_id=record.chunk.id,
        stable_id=record.chunk.stable_id,
        document_id=record.document.id,
        document_title=record.document.title,
        document_version_id=record.version.id,
        document_version=record.version.version_number,
        source_kind=record.document.source_kind,
        created_at=record.document.created_at,
        updated_at=record.document.updated_at,
        ordinal=record.chunk.ordinal,
        text=record.chunk.text,
        text_sha256=record.chunk.text_sha256,
        token_count=record.chunk.token_count,
        provenance=dict(record.chunk.provenance),
        score=max(0.0, min(score, 1.0)),
        lexical_score=lexical_score,
        semantic_score=semantic_score,
        tag_names=record.tag_names,
        debug=debug,
    )


def _replace_candidate_score(
    candidate: RetrievedCandidate,
    *,
    score: float,
    lexical_score: float | None,
    semantic_score: float | None,
    debug: dict[str, object],
) -> RetrievedCandidate:
    return RetrievedCandidate(
        chunk_id=candidate.chunk_id,
        stable_id=candidate.stable_id,
        document_id=candidate.document_id,
        document_title=candidate.document_title,
        document_version_id=candidate.document_version_id,
        document_version=candidate.document_version,
        source_kind=candidate.source_kind,
        created_at=candidate.created_at,
        updated_at=candidate.updated_at,
        ordinal=candidate.ordinal,
        text=candidate.text,
        text_sha256=candidate.text_sha256,
        token_count=candidate.token_count,
        provenance=candidate.provenance,
        score=max(0.0, min(score, 1.0)),
        lexical_score=lexical_score,
        semantic_score=semantic_score,
        tag_names=candidate.tag_names,
        debug=debug,
    )


def _rank(candidates: list[RetrievedCandidate], *, limit: int) -> tuple[RetrievedCandidate, ...]:
    ranked = sorted(candidates, key=lambda candidate: candidate.score, reverse=True)[:limit]
    return tuple(
        RetrievedCandidate(
            chunk_id=candidate.chunk_id,
            stable_id=candidate.stable_id,
            document_id=candidate.document_id,
            document_title=candidate.document_title,
            document_version_id=candidate.document_version_id,
            document_version=candidate.document_version,
            source_kind=candidate.source_kind,
            created_at=candidate.created_at,
            updated_at=candidate.updated_at,
            ordinal=candidate.ordinal,
            text=candidate.text,
            text_sha256=candidate.text_sha256,
            token_count=candidate.token_count,
            provenance=candidate.provenance,
            score=candidate.score,
            lexical_score=candidate.lexical_score,
            semantic_score=candidate.semantic_score,
            rank=index,
            tag_names=candidate.tag_names,
            debug=candidate.debug,
        )
        for index, candidate in enumerate(ranked, start=1)
    )


def _excerpt(text_value: str, *, limit: int = 700) -> str:
    collapsed = " ".join(text_value.split())
    if len(collapsed) <= limit:
        return collapsed
    return f"{collapsed[: limit - 1].rstrip()}..."


def _as_float_list(value: object) -> list[float]:
    if isinstance(value, list):
        return [float(item) for item in value]
    return []


def _dialect_name(session: AsyncSession) -> str:
    bind = session.get_bind()
    return bind.dialect.name
