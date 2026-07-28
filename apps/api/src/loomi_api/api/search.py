from __future__ import annotations

from datetime import datetime
from time import perf_counter
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from loomi_api.api.dependencies import DbSession, OwnerContext, get_settings_from_app
from loomi_api.chat.service import candidate_payload, context_payload
from loomi_api.retrieval.contracts import RetrievalQuery, SearchFilters, SearchMode
from loomi_api.retrieval.service import RetrievalError, RetrievalService

router = APIRouter(prefix="/api/v1/search", tags=["search"])


class SearchFiltersPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_ids: list[str] = Field(default_factory=list, max_length=50)
    collection_ids: list[str] = Field(default_factory=list, max_length=50)
    tags: list[str] = Field(default_factory=list, max_length=25)
    source_types: list[str] = Field(default_factory=list, max_length=20)
    created_from: datetime | None = None
    created_to: datetime | None = None


class SearchRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    query: str = Field(min_length=2, max_length=500)
    mode: SearchMode = "hybrid"
    filters: SearchFiltersPayload = Field(default_factory=SearchFiltersPayload)
    limit: int = Field(default=10, ge=1, le=50)
    offset: int = Field(default=0, ge=0)
    min_score: float = Field(default=0.0, ge=0, le=1)
    debug: bool = False


class SearchResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: SearchMode
    query: str
    items: list[dict[str, object]]
    selected_context: list[dict[str, object]]
    total: int
    limit: int
    offset: int
    latency_ms: int
    warnings: list[str]
    request_id: str
    trace_id: str
    debug: dict[str, object] | None = None


@router.post("", response_model=SearchResponse)
async def search(
    request: Request,
    payload: SearchRequest,
    session: DbSession,
    owner: OwnerContext,
) -> SearchResponse:
    return await _run_search(request, payload, session, owner)


@router.post("/{mode}", response_model=SearchResponse)
async def search_mode(
    mode: Literal["lexical", "semantic", "hybrid"],
    request: Request,
    payload: SearchRequest,
    session: DbSession,
    owner: OwnerContext,
) -> SearchResponse:
    return await _run_search(request, payload.model_copy(update={"mode": mode}), session, owner)


async def _run_search(
    request: Request,
    payload: SearchRequest,
    session: DbSession,
    owner: OwnerContext,
) -> SearchResponse:
    started = perf_counter()
    settings = get_settings_from_app(request)
    filters = SearchFilters(
        document_ids=tuple(payload.filters.document_ids),
        collection_ids=tuple(payload.filters.collection_ids),
        tags=tuple(tag.casefold() for tag in payload.filters.tags),
        source_types=tuple(payload.filters.source_types),
        created_from=payload.filters.created_from,
        created_to=payload.filters.created_to,
    )
    try:
        result = await RetrievalService(settings).search(
            session,
            RetrievalQuery(
                owner_user_id=owner.user.id,
                query=payload.query,
                mode=payload.mode,
                filters=filters,
                limit=payload.limit,
                offset=payload.offset,
                min_score=payload.min_score,
                debug=payload.debug,
            ),
        )
    except RetrievalError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SearchResponse(
        mode=result.mode,
        query=result.query,
        items=[
            candidate_payload(candidate, debug=payload.debug) for candidate in result.candidates
        ],
        selected_context=[
            context_payload(item, debug=payload.debug) for item in result.selected_context
        ],
        total=result.total,
        limit=payload.limit,
        offset=payload.offset,
        latency_ms=round((perf_counter() - started) * 1000),
        warnings=list(result.warnings),
        request_id=str(getattr(request.state, "request_id", "")),
        trace_id=str(getattr(request.state, "trace_id", "")),
        debug=result.debug if payload.debug else None,
    )
