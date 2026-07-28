from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from loomi_api.api.dependencies import (
    CsrfOwnerContext,
    DbSession,
    OwnerContext,
    get_settings_from_app,
)
from loomi_api.chat.service import (
    ChatRunOptions,
    cancel_run,
    create_retry_run,
    create_stream_run,
    load_owner_conversation,
    load_source_chunk,
    source_locator,
    stream_run_events,
)
from loomi_api.db.base import utc_now
from loomi_api.db.models import Conversation, Message, MessageCitation
from loomi_api.retrieval.contracts import SearchFilters, SearchMode

router = APIRouter(prefix="/api/v1", tags=["conversations"])


class ConversationSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None


class MessagePayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    conversation_id: str
    role: str
    content: str
    model: str | None
    token_count: int | None
    created_at: datetime
    citations: list[dict[str, object]] = Field(default_factory=list)


class ConversationDetail(ConversationSummary):
    messages: list[MessagePayload] = Field(default_factory=list)


class CreateConversationRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)


class UpdateConversationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)


class CreateMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=5000)


class ChatFiltersPayload(BaseModel):
    document_ids: list[str] = Field(default_factory=list, max_length=50)
    collection_ids: list[str] = Field(default_factory=list, max_length=50)
    tags: list[str] = Field(default_factory=list, max_length=25)
    source_types: list[str] = Field(default_factory=list, max_length=20)
    created_from: datetime | None = None
    created_to: datetime | None = None


class StreamChatRequest(BaseModel):
    content: str = Field(min_length=1, max_length=5000)
    mode: SearchMode = "hybrid"
    filters: ChatFiltersPayload = Field(default_factory=ChatFiltersPayload)
    provider: (
        Literal["mock", "openai-compatible", "openai", "anthropic", "gemini", "vllm"] | None
    ) = None
    model: str | None = Field(default=None, max_length=160)
    min_score: float = Field(default=0.12, ge=0, le=1)
    debug: bool = False


class RunActionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    state: str


class RunCreateResponse(RunActionResponse):
    conversation_id: str
    message_id: str


class SourceChunkResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    chunk_id: str
    document_id: str
    document_title: str
    document_version: int
    document_version_id: str
    text: str
    excerpt: str
    provenance: dict[str, object]
    source_preview_locator: str


@router.get("/conversations", response_model=list[ConversationSummary])
async def list_conversations(
    session: DbSession,
    owner: OwnerContext,
) -> list[ConversationSummary]:
    conversations = list(
        await session.scalars(
            select(Conversation)
            .where(
                Conversation.owner_user_id == owner.user.id,
                Conversation.archived_at.is_(None),
            )
            .order_by(desc(Conversation.updated_at))
        )
    )
    return [_conversation_summary(conversation) for conversation in conversations]


@router.post("/conversations", response_model=ConversationSummary, status_code=201)
async def create_conversation(
    payload: CreateConversationRequest,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> ConversationSummary:
    conversation = Conversation(
        owner_user_id=owner.user.id,
        title=(payload.title or "New conversation").strip() or "New conversation",
    )
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return _conversation_summary(conversation)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: str,
    session: DbSession,
    owner: OwnerContext,
) -> ConversationDetail:
    conversation = await _load_conversation_http(session, owner.user.id, conversation_id)
    messages = list(
        await session.scalars(
            select(Message)
            .where(
                Message.conversation_id == conversation.id,
                Message.owner_user_id == owner.user.id,
            )
            .order_by(Message.created_at.asc())
        )
    )
    return ConversationDetail(
        **_conversation_summary(conversation).model_dump(),
        messages=[await _message_payload(session, message) for message in messages],
    )


@router.patch("/conversations/{conversation_id}", response_model=ConversationSummary)
async def update_conversation(
    conversation_id: str,
    payload: UpdateConversationRequest,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> ConversationSummary:
    conversation = await _load_conversation_http(session, owner.user.id, conversation_id)
    conversation.title = payload.title.strip()
    await session.commit()
    await session.refresh(conversation)
    return _conversation_summary(conversation)


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: str,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> None:
    conversation = await _load_conversation_http(session, owner.user.id, conversation_id)
    conversation.archived_at = utc_now()
    await session.commit()


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessagePayload,
    status_code=201,
)
async def create_message(
    conversation_id: str,
    payload: CreateMessageRequest,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> MessagePayload:
    conversation = await _load_conversation_http(session, owner.user.id, conversation_id)
    message = Message(
        conversation_id=conversation.id,
        owner_user_id=owner.user.id,
        role="user",
        content=payload.content.strip(),
        token_count=max(1, len(payload.content) // 4),
    )
    session.add(message)
    await session.commit()
    await session.refresh(message)
    return await _message_payload(session, message)


@router.post(
    "/conversations/{conversation_id}/runs",
    response_model=RunCreateResponse,
    status_code=202,
)
async def create_generation_run(
    request: Request,
    conversation_id: str,
    payload: StreamChatRequest,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> RunCreateResponse:
    request_id = str(getattr(request.state, "request_id", ""))
    trace_id = str(getattr(request.state, "trace_id", ""))
    try:
        created = await create_stream_run(
            session=session,
            owner_user_id=owner.user.id,
            conversation_id=conversation_id,
            options=_chat_options(payload),
            request_id=request_id,
            trace_id=trace_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RunCreateResponse(
        run_id=created.run_id,
        state="running",
        conversation_id=created.conversation_id,
        message_id=created.user_message_id,
    )


@router.post("/conversations/{conversation_id}/responses/stream")
async def stream_conversation_response(
    request: Request,
    conversation_id: str,
    payload: StreamChatRequest,
    session: DbSession,
    owner: CsrfOwnerContext,
    idempotency_key: Annotated[str | None, Header(alias="idempotency-key")] = None,
) -> StreamingResponse:
    del idempotency_key
    settings = get_settings_from_app(request)
    request_id = str(getattr(request.state, "request_id", ""))
    trace_id = str(getattr(request.state, "trace_id", ""))
    options = _chat_options(payload)
    try:
        created = await create_stream_run(
            session=session,
            owner_user_id=owner.user.id,
            conversation_id=conversation_id,
            options=options,
            request_id=request_id,
            trace_id=trace_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    sessionmaker = cast(async_sessionmaker[AsyncSession], request.app.state.db_sessionmaker)

    async def body() -> AsyncIterator[str]:
        async for event in stream_run_events(
            settings=settings,
            sessionmaker=sessionmaker,
            owner_user_id=owner.user.id,
            created=created,
            options=options,
            request_id=request_id,
            trace_id=trace_id,
        ):
            yield _sse(event)

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
    )


@router.post("/messages/{message_id}/retry/stream")
async def retry_message_response(
    request: Request,
    message_id: str,
    payload: StreamChatRequest,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> StreamingResponse:
    settings = get_settings_from_app(request)
    request_id = str(getattr(request.state, "request_id", ""))
    trace_id = str(getattr(request.state, "trace_id", ""))
    options = _chat_options(payload)
    try:
        created = await create_retry_run(
            session=session,
            owner_user_id=owner.user.id,
            user_message_id=message_id,
            options=options,
            request_id=request_id,
            trace_id=trace_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    sessionmaker = cast(async_sessionmaker[AsyncSession], request.app.state.db_sessionmaker)

    async def body() -> AsyncIterator[str]:
        async for event in stream_run_events(
            settings=settings,
            sessionmaker=sessionmaker,
            owner_user_id=owner.user.id,
            created=created,
            options=options,
            request_id=request_id,
            trace_id=trace_id,
        ):
            yield _sse(event)

    return StreamingResponse(body(), media_type="text/event-stream")


@router.post("/runs/{run_id}/cancel", response_model=RunActionResponse)
async def cancel_generation(
    run_id: str,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> RunActionResponse:
    try:
        run = await cancel_run(session, owner.user.id, run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RunActionResponse(run_id=run.id, state=run.state)


@router.get("/sources/chunks/{chunk_id}", response_model=SourceChunkResponse)
async def get_source_chunk(
    chunk_id: str,
    session: DbSession,
    owner: OwnerContext,
) -> SourceChunkResponse:
    try:
        chunk, document, version = await load_source_chunk(session, owner.user.id, chunk_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    excerpt = " ".join(chunk.text.split())
    if len(excerpt) > 700:
        excerpt = f"{excerpt[:699].rstrip()}..."
    return SourceChunkResponse(
        chunk_id=chunk.id,
        document_id=document.id,
        document_title=document.title,
        document_version=version.version_number,
        document_version_id=version.id,
        text=chunk.text,
        excerpt=excerpt,
        provenance=chunk.provenance,
        source_preview_locator=source_locator(chunk.id),
    )


def _chat_options(payload: StreamChatRequest) -> ChatRunOptions:
    return ChatRunOptions(
        content=payload.content,
        mode=payload.mode,
        filters=SearchFilters(
            document_ids=tuple(payload.filters.document_ids),
            collection_ids=tuple(payload.filters.collection_ids),
            tags=tuple(tag.casefold() for tag in payload.filters.tags),
            source_types=tuple(payload.filters.source_types),
            created_from=payload.filters.created_from,
            created_to=payload.filters.created_to,
        ),
        provider=payload.provider,
        model=payload.model,
        min_score=payload.min_score,
        debug=payload.debug,
    )


async def _load_conversation_http(
    session: AsyncSession,
    owner_user_id: str,
    conversation_id: str,
) -> Conversation:
    try:
        return await load_owner_conversation(session, owner_user_id, conversation_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _conversation_summary(conversation: Conversation) -> ConversationSummary:
    return ConversationSummary(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        archived_at=conversation.archived_at,
    )


async def _message_payload(session: AsyncSession, message: Message) -> MessagePayload:
    rows = list(
        (
            await session.execute(
                select(MessageCitation)
                .where(MessageCitation.message_id == message.id)
                .order_by(MessageCitation.created_at.asc())
            )
        ).scalars()
    )
    citations: list[dict[str, object]] = []
    for row in rows:
        citations.append(
            {
                "chunk_id": row.chunk_id,
                "quote": row.quote,
                **row.citation_metadata,
            }
        )
    return MessagePayload(
        id=message.id,
        conversation_id=message.conversation_id,
        role=message.role,
        content=message.content,
        model=message.model,
        token_count=message.token_count,
        created_at=message.created_at,
        citations=citations,
    )


def _sse(event: dict[str, object]) -> str:
    return f"event: {event['event']}\ndata: {json.dumps(event['data'], default=str)}\n\n"
