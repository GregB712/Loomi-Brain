from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, cast

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from loomi_api.config import Settings
from loomi_api.db.models import (
    AgentEvent,
    AgentRun,
    Chunk,
    Conversation,
    Document,
    DocumentVersion,
    Message,
    MessageCitation,
)
from loomi_api.model_gateway.contracts import ModelRequest, ProviderError, ProviderName
from loomi_api.model_gateway.providers import ProviderGateway
from loomi_api.observability.prompts import get_prompt
from loomi_api.observability.telemetry import elapsed_ms, record_span, start_timer
from loomi_api.retrieval.contracts import (
    ContextItem,
    RetrievalQuery,
    RetrievedCandidate,
    SearchFilters,
    SearchMode,
)
from loomi_api.retrieval.service import RetrievalConfig, RetrievalService

RunState = Literal["created", "running", "completed", "cancelled", "failed"]


@dataclass(frozen=True)
class ChatRunOptions:
    content: str
    mode: SearchMode = "hybrid"
    filters: SearchFilters = SearchFilters()
    provider: ProviderName | None = None
    model: str | None = None
    min_score: float = 0.12
    debug: bool = False


@dataclass(frozen=True)
class CreatedRun:
    conversation_id: str
    user_message_id: str
    run_id: str


async def create_stream_run(
    *,
    session: AsyncSession,
    owner_user_id: str,
    conversation_id: str,
    options: ChatRunOptions,
    request_id: str,
    trace_id: str,
) -> CreatedRun:
    conversation = await load_owner_conversation(session, owner_user_id, conversation_id)
    user_message = Message(
        conversation_id=conversation.id,
        owner_user_id=owner_user_id,
        role="user",
        content=options.content.strip(),
        token_count=_estimate_tokens(options.content),
    )
    session.add(user_message)
    if conversation.title == "New conversation":
        conversation.title = _title_from_message(options.content)
    run = AgentRun(
        owner_user_id=owner_user_id,
        conversation_id=conversation.id,
        state="running",
        trace_id=trace_id,
        budget={
            "request_id": request_id,
            "search_mode": options.mode,
            "provider": options.provider,
            "model": options.model,
            "min_score": options.min_score,
            "filters": _filters_payload(options.filters),
        },
    )
    session.add(run)
    await session.flush()
    await _record_event(
        session,
        run.id,
        "run_started",
        {
            "run_id": run.id,
            "conversation_id": conversation.id,
            "message_id": user_message.id,
            "request_id": request_id,
            "trace_id": trace_id,
        },
    )
    await session.commit()
    return CreatedRun(
        conversation_id=conversation.id,
        user_message_id=user_message.id,
        run_id=run.id,
    )


async def create_retry_run(
    *,
    session: AsyncSession,
    owner_user_id: str,
    user_message_id: str,
    options: ChatRunOptions,
    request_id: str,
    trace_id: str,
) -> CreatedRun:
    user_message = await session.scalar(
        select(Message).where(
            Message.id == user_message_id,
            Message.owner_user_id == owner_user_id,
            Message.role == "user",
        )
    )
    if user_message is None:
        raise LookupError("Message not found.")
    conversation = await load_owner_conversation(
        session,
        owner_user_id,
        user_message.conversation_id,
    )
    run = AgentRun(
        owner_user_id=owner_user_id,
        conversation_id=conversation.id,
        state="running",
        trace_id=trace_id,
        budget={
            "request_id": request_id,
            "search_mode": options.mode,
            "provider": options.provider,
            "model": options.model,
            "min_score": options.min_score,
            "filters": _filters_payload(options.filters),
            "retry_of_message_id": user_message.id,
        },
    )
    session.add(run)
    await session.flush()
    await _record_event(
        session,
        run.id,
        "run_started",
        {
            "run_id": run.id,
            "conversation_id": conversation.id,
            "message_id": user_message.id,
            "request_id": request_id,
            "trace_id": trace_id,
        },
    )
    await session.commit()
    return CreatedRun(
        conversation_id=conversation.id,
        user_message_id=user_message.id,
        run_id=run.id,
    )


async def stream_run_events(
    *,
    settings: Settings,
    sessionmaker: async_sessionmaker[AsyncSession],
    owner_user_id: str,
    created: CreatedRun,
    options: ChatRunOptions,
    request_id: str,
    trace_id: str,
) -> AsyncIterator[dict[str, object]]:
    started = time.perf_counter()
    warnings: list[str] = []
    answer_parts: list[str] = []
    raw_citation_ids: list[str] = []
    usage_payload: dict[str, object] | None = None
    provider_name: ProviderName = options.provider or settings.chat_provider
    model = options.model or settings.chat_model
    async with sessionmaker() as session:
        try:
            yield await _event(
                session,
                created.run_id,
                "run_started",
                {
                    "run_id": created.run_id,
                    "conversation_id": created.conversation_id,
                    "message_id": created.user_message_id,
                    "request_id": request_id,
                    "trace_id": trace_id,
                },
            )
            user_message = await _load_owner_message(
                session,
                owner_user_id,
                created.user_message_id,
            )
            yield await _event(
                session,
                created.run_id,
                "retrieval_started",
                {"mode": options.mode, "query": user_message.content},
            )
            retrieval_query = RetrievalQuery(
                owner_user_id=owner_user_id,
                query=user_message.content,
                mode=options.mode,
                filters=options.filters,
                limit=12,
                min_score=options.min_score,
                debug=options.debug,
                request_id=request_id,
                trace_id=trace_id,
            )
            retrieval = await RetrievalService(settings, RetrievalConfig()).search(
                session,
                retrieval_query,
            )
            selected_context = _sufficient_context(retrieval.selected_context)
            if not selected_context:
                warnings.append("insufficient_evidence")
            yield await _event(
                session,
                created.run_id,
                "retrieval_completed",
                {
                    "mode": retrieval.mode,
                    "total": retrieval.total,
                    "retrieved_candidates": [
                        candidate_payload(candidate, debug=options.debug)
                        for candidate in retrieval.candidates
                    ],
                    "selected_context": [
                        context_payload(item, debug=options.debug) for item in selected_context
                    ],
                    "warnings": [*retrieval.warnings, *warnings],
                },
            )

            provider = ProviderGateway(settings).provider_for(provider_name)
            prompt = get_prompt("grounded_chat")
            run = await _load_run(session, created.run_id, owner_user_id)
            run.provider = provider_name
            run.model = model
            run.trace_metadata = {
                **(run.trace_metadata or {}),
                "prompt_id": prompt.stable_id,
                "prompt_version": prompt.version,
                "selected_context_count": len(selected_context),
            }

            async def is_cancelled() -> bool:
                run = await _load_run(session, created.run_id, owner_user_id)
                await session.refresh(run)
                return run.state == "cancelled"

            model_request = ModelRequest(
                provider=provider_name,
                model=model,
                owner_request=user_message.content,
                context=selected_context,
                request_id=request_id,
                trace_id=trace_id,
                max_output_tokens=settings.model_max_output_tokens,
            )
            model_started = start_timer()
            try:
                async for delta in provider.stream_chat(model_request, is_cancelled):
                    if await is_cancelled():
                        await record_span(
                            session,
                            settings,
                            name="loomi.model.generation",
                            component="model",
                            trace_id=trace_id,
                            owner_user_id=owner_user_id,
                            status="cancelled",
                            duration_ms=elapsed_ms(model_started),
                            attributes=_model_span_attributes(
                                provider=provider_name,
                                model=model,
                                prompt_id=prompt.stable_id,
                                prompt_version=prompt.version,
                                selected_context_count=len(selected_context),
                                usage=usage_payload,
                                request_id=request_id,
                                trace_id=trace_id,
                            ),
                        )
                        await _set_run_state(session, created.run_id, owner_user_id, "cancelled")
                        yield await _event(
                            session,
                            created.run_id,
                            "cancelled",
                            {"run_id": created.run_id},
                        )
                        return
                    if delta.delta_type == "token":
                        answer_parts.append(delta.text)
                        yield await _event(
                            session, created.run_id, "token_delta", {"text": delta.text}
                        )
                    elif delta.delta_type == "citation" and delta.citation_id:
                        raw_citation_ids.append(delta.citation_id)
                    elif delta.delta_type == "warning" and delta.warning:
                        warnings.append(delta.warning)
                        yield await _event(
                            session, created.run_id, "warning", {"code": delta.warning}
                        )
                    elif delta.delta_type == "completed" and delta.usage is not None:
                        usage_payload = {
                            "input_tokens": delta.usage.input_tokens,
                            "output_tokens": delta.usage.output_tokens,
                            "total_tokens": delta.usage.total_tokens,
                            "estimated_cost_usd": delta.usage.estimated_cost_usd,
                        }
            except ProviderError as exc:
                await record_span(
                    session,
                    settings,
                    name="loomi.model.generation",
                    component="model",
                    trace_id=trace_id,
                    owner_user_id=owner_user_id,
                    status="error",
                    duration_ms=elapsed_ms(model_started),
                    error_code=exc.code,
                    attributes=_model_span_attributes(
                        provider=provider_name,
                        model=model,
                        prompt_id=prompt.stable_id,
                        prompt_version=prompt.version,
                        selected_context_count=len(selected_context),
                        usage=usage_payload,
                        request_id=request_id,
                        trace_id=trace_id,
                        error_code=exc.code,
                    ),
                )
                raise
            await record_span(
                session,
                settings,
                name="loomi.model.generation",
                component="model",
                trace_id=trace_id,
                owner_user_id=owner_user_id,
                duration_ms=elapsed_ms(model_started),
                attributes=_model_span_attributes(
                    provider=provider_name,
                    model=model,
                    prompt_id=prompt.stable_id,
                    prompt_version=prompt.version,
                    selected_context_count=len(selected_context),
                    usage=usage_payload,
                    request_id=request_id,
                    trace_id=trace_id,
                ),
            )
            answer_text = "".join(answer_parts).strip()
            valid_citations, invalid_ids = validate_citations(raw_citation_ids, selected_context)
            if invalid_ids:
                warnings.append("invalid_citations_removed")
                yield await _event(
                    session,
                    created.run_id,
                    "warning",
                    {"code": "invalid_citations_removed", "invalid_ids": invalid_ids},
                )
            assistant = Message(
                conversation_id=created.conversation_id,
                owner_user_id=owner_user_id,
                role="assistant",
                content=answer_text,
                model=model,
                token_count=_estimate_tokens(answer_text),
            )
            session.add(assistant)
            await session.flush()
            for citation in valid_citations:
                session.add(
                    MessageCitation(
                        message_id=assistant.id,
                        chunk_id=citation.candidate.chunk_id,
                        quote=citation.excerpt,
                        citation_metadata={
                            "allowed_citation_id": citation.allowed_citation_id,
                            "document_id": citation.candidate.document_id,
                            "document_title": citation.candidate.document_title,
                            "document_version": citation.candidate.document_version,
                            "document_version_id": citation.candidate.document_version_id,
                            "source_preview_locator": source_locator(citation.candidate.chunk_id),
                            "provenance": citation.candidate.provenance,
                        },
                    )
                )
            latency_ms = round((time.perf_counter() - started) * 1000)
            completed_payload = {
                "answer_text": answer_text,
                "message_id": assistant.id,
                "citations": [citation_payload(citation) for citation in valid_citations],
                "retrieved_candidates": [
                    candidate_payload(candidate, debug=options.debug)
                    for candidate in retrieval.candidates
                ],
                "selected_context": [
                    context_payload(item, debug=options.debug) for item in selected_context
                ],
                "provider": provider_name,
                "model": model,
                "usage": usage_payload
                or {
                    "input_tokens": 0,
                    "output_tokens": _estimate_tokens(answer_text),
                    "total_tokens": _estimate_tokens(answer_text),
                    "estimated_cost_usd": 0,
                },
                "latency_ms": latency_ms,
                "warnings": sorted(set(warnings)),
                "request_id": request_id,
                "trace_id": trace_id,
                "run_id": created.run_id,
            }
            usage_event = cast(dict[str, object], completed_payload["usage"])
            yield await _event(session, created.run_id, "usage", usage_event)
            for citation in valid_citations:
                yield await _event(session, created.run_id, "citation", citation_payload(citation))
            await _set_run_state(session, created.run_id, owner_user_id, "completed")
            yield await _event(session, created.run_id, "completed", completed_payload)
        except asyncio.CancelledError:
            await _set_run_state(session, created.run_id, owner_user_id, "cancelled")
            raise
        except ProviderError as exc:
            await _set_run_state(session, created.run_id, owner_user_id, "failed")
            yield await _event(
                session,
                created.run_id,
                "failed",
                {
                    "code": exc.code,
                    "detail": exc.detail,
                    "request_id": request_id,
                    "trace_id": trace_id,
                },
            )
        except Exception:
            await _set_run_state(session, created.run_id, owner_user_id, "failed")
            yield await _event(
                session,
                created.run_id,
                "failed",
                {
                    "code": "chat_generation_failed",
                    "detail": "The assistant response could not be generated safely.",
                    "request_id": request_id,
                    "trace_id": trace_id,
                },
            )


async def cancel_run(session: AsyncSession, owner_user_id: str, run_id: str) -> AgentRun:
    run = await _load_run(session, run_id, owner_user_id)
    if run.state not in {"completed", "complete", "cancelled", "failed"}:
        run.state = "cancelled"
        await _record_event(session, run.id, "cancelled", {"run_id": run.id})
        await session.commit()
    return run


async def load_owner_conversation(
    session: AsyncSession,
    owner_user_id: str,
    conversation_id: str,
) -> Conversation:
    conversation = await session.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.owner_user_id == owner_user_id,
            Conversation.archived_at.is_(None),
        )
    )
    if conversation is None:
        raise LookupError("Conversation not found.")
    return conversation


async def _load_owner_message(
    session: AsyncSession,
    owner_user_id: str,
    message_id: str,
) -> Message:
    message = await session.scalar(
        select(Message).where(Message.id == message_id, Message.owner_user_id == owner_user_id)
    )
    if message is None:
        raise LookupError("Message not found.")
    return message


async def _load_run(session: AsyncSession, run_id: str, owner_user_id: str) -> AgentRun:
    run = await session.scalar(
        select(AgentRun).where(AgentRun.id == run_id, AgentRun.owner_user_id == owner_user_id)
    )
    if run is None:
        raise LookupError("Run not found.")
    return run


async def _set_run_state(
    session: AsyncSession,
    run_id: str,
    owner_user_id: str,
    state: RunState,
) -> None:
    run = await _load_run(session, run_id, owner_user_id)
    run.state = state
    await session.commit()


async def _event(
    session: AsyncSession,
    run_id: str,
    event_type: str,
    payload: dict[str, object],
) -> dict[str, object]:
    await _record_event(session, run_id, event_type, payload)
    await session.commit()
    return {"event": event_type, "data": payload}


async def _record_event(
    session: AsyncSession,
    run_id: str,
    event_type: str,
    payload: dict[str, object],
) -> None:
    max_sequence = await session.scalar(
        select(AgentEvent.sequence_number)
        .where(AgentEvent.run_id == run_id)
        .order_by(desc(AgentEvent.sequence_number))
        .limit(1)
    )
    session.add(
        AgentEvent(
            run_id=run_id,
            event_type=event_type,
            sequence_number=int(max_sequence or 0) + 1,
            payload=json.loads(json.dumps(payload, default=str)),
        )
    )


def _model_span_attributes(
    *,
    provider: ProviderName,
    model: str,
    prompt_id: str,
    prompt_version: str,
    selected_context_count: int,
    usage: dict[str, object] | None,
    request_id: str,
    trace_id: str,
    error_code: str | None = None,
) -> dict[str, object]:
    usage_payload = usage or {}
    return {
        "provider": provider,
        "model": model,
        "prompt_id": prompt_id,
        "prompt_version": prompt_version,
        "selected_context_count": selected_context_count,
        "input_tokens": usage_payload.get("input_tokens", 0),
        "output_tokens": usage_payload.get("output_tokens", 0),
        "total_tokens": usage_payload.get("total_tokens", 0),
        "estimated_cost_usd": usage_payload.get("estimated_cost_usd", 0),
        "request_id": request_id,
        "trace_id": trace_id,
        "error_code": error_code,
    }


def validate_citations(
    citation_ids: list[str],
    selected_context: tuple[ContextItem, ...],
) -> tuple[tuple[ContextItem, ...], tuple[str, ...]]:
    allowed = {item.allowed_citation_id: item for item in selected_context}
    valid: list[ContextItem] = []
    invalid: list[str] = []
    for citation_id in dict.fromkeys(citation_ids):
        item = allowed.get(citation_id)
        if item is None:
            invalid.append(citation_id)
        else:
            valid.append(item)
    return tuple(valid), tuple(invalid)


async def load_source_chunk(
    session: AsyncSession,
    owner_user_id: str,
    chunk_id: str,
) -> tuple[Chunk, Document, DocumentVersion]:
    row = (
        await session.execute(
            select(Chunk, Document, DocumentVersion)
            .join(Document, Document.id == Chunk.document_id)
            .join(DocumentVersion, DocumentVersion.id == Chunk.document_version_id)
            .where(
                Chunk.id == chunk_id,
                Chunk.owner_user_id == owner_user_id,
                Document.owner_user_id == owner_user_id,
                Document.deleted_at.is_(None),
            )
        )
    ).one_or_none()
    if row is None:
        raise LookupError("Source chunk not found.")
    return cast(tuple[Chunk, Document, DocumentVersion], row)


def candidate_payload(candidate: object, *, debug: bool = False) -> dict[str, object]:
    typed = cast(RetrievedCandidate, candidate)
    payload: dict[str, object] = {
        "chunk_id": typed.chunk_id,
        "document_id": typed.document_id,
        "document_title": typed.document_title,
        "document_version": typed.document_version,
        "document_version_id": typed.document_version_id,
        "source_kind": typed.source_kind,
        "ordinal": typed.ordinal,
        "score": round(typed.score, 4),
        "lexical_score": (
            round(typed.lexical_score, 4) if typed.lexical_score is not None else None
        ),
        "semantic_score": (
            round(typed.semantic_score, 4) if typed.semantic_score is not None else None
        ),
        "excerpt": _excerpt(typed.text),
        "provenance": typed.provenance,
        "source_preview_locator": source_locator(typed.chunk_id),
        "tag_names": list(typed.tag_names),
    }
    if debug:
        payload["debug"] = typed.debug
    return payload


def context_payload(item: ContextItem, *, debug: bool = False) -> dict[str, object]:
    payload = candidate_payload(item.candidate, debug=debug)
    payload["allowed_citation_id"] = item.allowed_citation_id
    payload["excerpt"] = item.excerpt
    return payload


def citation_payload(item: ContextItem) -> dict[str, object]:
    locator = source_locator(item.candidate.chunk_id)
    return {
        "citation_id": item.allowed_citation_id,
        "chunk_id": item.candidate.chunk_id,
        "document_id": item.candidate.document_id,
        "document_title": item.candidate.document_title,
        "document_version": item.candidate.document_version,
        "document_version_id": item.candidate.document_version_id,
        "page": item.candidate.provenance.get("page_number"),
        "slide": item.candidate.provenance.get("slide_number"),
        "sheet": item.candidate.provenance.get("sheet_name"),
        "section": item.candidate.provenance.get("heading_path"),
        "excerpt": item.excerpt,
        "source_preview_locator": locator,
    }


def source_locator(chunk_id: str) -> str:
    return f"/api/v1/sources/chunks/{chunk_id}"


def _sufficient_context(context: tuple[ContextItem, ...]) -> tuple[ContextItem, ...]:
    if not context:
        return ()
    sufficient = [
        item
        for item in context
        if item.candidate.lexical_score is not None and item.candidate.lexical_score > 0.08
    ]
    return tuple(sufficient)


def _filters_payload(filters: SearchFilters) -> dict[str, object]:
    return {
        "document_ids": list(filters.document_ids),
        "collection_ids": list(filters.collection_ids),
        "tags": list(filters.tags),
        "source_types": list(filters.source_types),
        "created_from": filters.created_from.isoformat() if filters.created_from else None,
        "created_to": filters.created_to.isoformat() if filters.created_to else None,
    }


def _title_from_message(content: str) -> str:
    words = [word.strip(".,:;!?()[]{}") for word in content.split() if word.strip()]
    title = " ".join(words[:8]).strip()
    if not title:
        return "New conversation"
    if len(title) > 80:
        return f"{title[:77].rstrip()}..."
    return title


def _estimate_tokens(value: str) -> int:
    return max(1, len(value) // 4)


def _excerpt(value: str, limit: int = 700) -> str:
    collapsed = " ".join(value.split())
    if len(collapsed) <= limit:
        return collapsed
    return f"{collapsed[: limit - 1].rstrip()}..."
