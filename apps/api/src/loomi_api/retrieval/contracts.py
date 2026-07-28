from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

SearchMode = Literal["lexical", "semantic", "hybrid"]


@dataclass(frozen=True)
class SearchFilters:
    document_ids: tuple[str, ...] = ()
    collection_ids: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    source_types: tuple[str, ...] = ()
    created_from: datetime | None = None
    created_to: datetime | None = None


@dataclass(frozen=True)
class RetrievalQuery:
    owner_user_id: str
    query: str
    mode: SearchMode
    filters: SearchFilters = field(default_factory=SearchFilters)
    limit: int = 10
    offset: int = 0
    min_score: float = 0.0
    debug: bool = False


@dataclass(frozen=True)
class RetrievedCandidate:
    chunk_id: str
    stable_id: str
    document_id: str
    document_title: str
    document_version_id: str
    document_version: int
    source_kind: str
    created_at: datetime
    updated_at: datetime
    ordinal: int
    text: str
    text_sha256: str
    token_count: int
    provenance: dict[str, object]
    score: float
    lexical_score: float | None = None
    semantic_score: float | None = None
    rank: int | None = None
    tag_names: tuple[str, ...] = ()
    debug: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ContextItem:
    allowed_citation_id: str
    candidate: RetrievedCandidate
    excerpt: str


@dataclass(frozen=True)
class RetrievalResult:
    mode: SearchMode
    query: str
    candidates: tuple[RetrievedCandidate, ...]
    selected_context: tuple[ContextItem, ...]
    total: int
    warnings: tuple[str, ...] = ()
    debug: dict[str, object] = field(default_factory=dict)


class Retriever(Protocol):
    async def retrieve(
        self,
        session: AsyncSession,
        query: RetrievalQuery,
    ) -> tuple[RetrievedCandidate, ...]:
        """Return ranked candidates for a query."""


class Reranker(Protocol):
    async def rerank(
        self,
        query: str,
        candidates: tuple[RetrievedCandidate, ...],
    ) -> tuple[RetrievedCandidate, ...]:
        """Optionally rerank retrieved candidates."""


class ContextAssembler(Protocol):
    def assemble(
        self,
        *,
        query: RetrievalQuery,
        candidates: tuple[RetrievedCandidate, ...],
    ) -> tuple[ContextItem, ...]:
        """Select bounded, deduplicated context for generation."""
