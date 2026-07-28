from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from loomi_api.agent_runtime.contracts import AgentRunLimits, AgentRunRequest
from loomi_api.agent_runtime.runtime import DEFAULT_ALLOWED_TOOLS, AgentRuntimeService
from loomi_api.api.dependencies import (
    CsrfOwnerContext,
    DbSession,
    OwnerContext,
    get_settings_from_app,
)

router = APIRouter(prefix="/api/v1/agent-runs", tags=["agent-runs"])


class AgentRunLimitsPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_steps: int = Field(default=16, ge=1, le=64)
    max_tool_calls: int = Field(default=3, ge=0, le=12)
    request_timeout_seconds: int = Field(default=45, ge=1, le=300)
    per_step_timeout_seconds: int = Field(default=10, ge=1, le=60)
    token_budget: int = Field(default=6000, ge=1, le=50_000)
    cost_budget_usd: float = Field(default=0.25, ge=0, le=50)
    max_retries: int = Field(default=1, ge=0, le=5)


class CreateAgentRunRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    owner_request: str = Field(min_length=1, max_length=5000)
    allowed_tools: list[str] = Field(
        default_factory=lambda: list(DEFAULT_ALLOWED_TOOLS),
        max_length=20,
    )
    limits: AgentRunLimitsPayload = Field(default_factory=AgentRunLimitsPayload)
    provider: str | None = Field(default=None, max_length=80)
    model: str | None = Field(default=None, max_length=160)


class ApprovalDecisionRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    arguments: dict[str, Any] | None = None
    reason: str | None = Field(default=None, max_length=500)


@router.post("", status_code=202)
async def create_agent_run(
    request: Request,
    payload: CreateAgentRunRequest,
    session: DbSession,
    owner: CsrfOwnerContext,
    idempotency_key: Annotated[str | None, Header(alias="idempotency-key")] = None,
) -> dict[str, Any]:
    service = _runtime(request, session)
    return await service.start(
        AgentRunRequest(
            owner_user_id=owner.user.id,
            owner_request=payload.owner_request,
            request_id=str(getattr(request.state, "request_id", "")),
            trace_id=str(getattr(request.state, "trace_id", "")),
            idempotency_key=idempotency_key,
            provider=payload.provider,
            model=payload.model,
            allowed_tools=tuple(payload.allowed_tools or DEFAULT_ALLOWED_TOOLS),
            limits=AgentRunLimits.from_mapping(payload.limits.model_dump()),
        )
    )


@router.get("")
async def list_agent_runs(
    request: Request,
    session: DbSession,
    owner: OwnerContext,
    state: str | None = Query(default=None, max_length=60),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    return await _runtime(request, session).list_runs(
        owner.user.id,
        state=state,
        limit=limit,
        offset=offset,
    )


@router.get("/{run_id}")
async def get_agent_run(
    run_id: str,
    request: Request,
    session: DbSession,
    owner: OwnerContext,
) -> dict[str, Any]:
    try:
        return await _runtime(request, session).detail(owner.user.id, run_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{run_id}/events")
async def get_agent_run_events(
    run_id: str,
    request: Request,
    session: DbSession,
    owner: OwnerContext,
) -> list[dict[str, Any]]:
    try:
        return await _runtime(request, session).event_history(owner.user.id, run_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{run_id}/stream")
async def stream_agent_run_events(
    run_id: str,
    request: Request,
    session: DbSession,
    owner: OwnerContext,
) -> StreamingResponse:
    try:
        events = await _runtime(request, session).event_history(owner.user.id, run_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    async def body() -> AsyncIterator[str]:
        for event in events:
            yield _sse({"event": event["event_type"], "data": event})

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
    )


@router.post("/{run_id}/cancel")
async def cancel_agent_run(
    run_id: str,
    request: Request,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> dict[str, Any]:
    try:
        return await _runtime(request, session).cancel(owner.user.id, run_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{run_id}/retry", status_code=202)
async def retry_agent_run(
    run_id: str,
    request: Request,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> dict[str, Any]:
    try:
        return await _runtime(request, session).retry(owner.user.id, run_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/{run_id}/approvals/{approval_id}/approve")
async def approve_agent_tool_call(
    run_id: str,
    approval_id: str,
    payload: ApprovalDecisionRequest,
    request: Request,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> dict[str, Any]:
    try:
        return await _runtime(request, session).approve(
            owner.user.id,
            run_id,
            approval_id,
            arguments=payload.arguments,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/{run_id}/approvals/{approval_id}/deny")
async def deny_agent_tool_call(
    run_id: str,
    approval_id: str,
    payload: ApprovalDecisionRequest,
    request: Request,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> dict[str, Any]:
    try:
        return await _runtime(request, session).deny(
            owner.user.id,
            run_id,
            approval_id,
            reason=payload.reason,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


def _runtime(request: Request, session: DbSession) -> AgentRuntimeService:
    return AgentRuntimeService(session=session, settings=get_settings_from_app(request))


def _sse(event: dict[str, Any]) -> str:
    return f"event: {event['event']}\ndata: {json.dumps(event['data'], default=str)}\n\n"
