from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from loomi_api.agent_runtime.contracts import AgentRunLimits, AgentRunRequest
from loomi_api.agent_runtime.runtime import AgentRuntimeService
from loomi_api.api.dependencies import (
    CsrfOwnerContext,
    DbSession,
    OwnerContext,
    get_settings_from_app,
)
from loomi_api.mcp_client.protocol import MCPClientError, canonical_mcp_tool_id
from loomi_api.mcp_client.service import MCPRegistryService
from loomi_api.mcp_client.templates import available_stdio_templates

router = APIRouter(prefix="/api/v1/mcp", tags=["mcp"])


class CreateMCPServerRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    transport: Literal["stdio", "streamable_http"]
    template_name: str | None = Field(default=None, max_length=80)
    url: str | None = Field(default=None, max_length=512)
    secret_ref: str | None = Field(default=None, max_length=255)
    environment_allowlist: list[str] = Field(default_factory=list, max_length=20)
    working_directory: str | None = Field(default=None, max_length=512)
    connection_timeout_seconds: int = Field(default=5, ge=1, le=30)
    tool_timeout_seconds: int = Field(default=10, ge=1, le=60)
    output_size_limit: int = Field(default=12_000, ge=512, le=128_000)
    allow_private_networks: bool = False


class UpdateMCPServerRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    secret_ref: str | None = Field(default=None, max_length=255)
    environment_allowlist: list[str] | None = Field(default=None, max_length=20)
    connection_timeout_seconds: int | None = Field(default=None, ge=1, le=30)
    tool_timeout_seconds: int | None = Field(default=None, ge=1, le=60)
    output_size_limit: int | None = Field(default=None, ge=512, le=128_000)
    allow_private_networks: bool | None = None


class CapabilityPolicyRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    enabled: bool
    risk_class: Literal[
        "read-only",
        "local-mutation",
        "external-mutation",
        "credential-sensitive",
        "destructive",
    ]
    approval_policy: Literal["never", "risk-based", "always"] = "risk-based"
    expected_side_effects: str | None = Field(default=None, max_length=500)
    confirm_broadening: bool = False


class InvokeMCPToolRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    arguments: dict[str, Any] = Field(default_factory=dict)
    owner_request: str | None = Field(default=None, max_length=1000)
    max_steps: int = Field(default=16, ge=4, le=64)
    max_tool_calls: int = Field(default=1, ge=1, le=4)


class DeleteMCPServerRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    confirm_name: str = Field(min_length=1, max_length=120)


@router.get("/templates")
async def list_mcp_templates(request: Request, owner: OwnerContext) -> dict[str, Any]:
    del owner
    if not get_settings_from_app(request).mcp_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MCP is disabled.",
        )
    return {"items": available_stdio_templates()}


@router.get("/servers")
async def list_mcp_servers(
    request: Request,
    session: DbSession,
    owner: OwnerContext,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    return await _service(request, session, owner.user.id).list_servers(limit=limit, offset=offset)


@router.post("/servers", status_code=201)
async def create_mcp_server(
    payload: CreateMCPServerRequest,
    request: Request,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> dict[str, Any]:
    try:
        return await _service(request, session, owner.user.id).create_server(payload.model_dump())
    except MCPClientError as exc:
        raise _http_error(exc) from exc


@router.get("/servers/{server_id}")
async def get_mcp_server(
    server_id: str,
    request: Request,
    session: DbSession,
    owner: OwnerContext,
) -> dict[str, Any]:
    try:
        return await _service(request, session, owner.user.id).get_server(server_id)
    except MCPClientError as exc:
        raise _http_error(exc) from exc


@router.patch("/servers/{server_id}")
async def update_mcp_server(
    server_id: str,
    payload: UpdateMCPServerRequest,
    request: Request,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> dict[str, Any]:
    try:
        return await _service(request, session, owner.user.id).update_server(
            server_id,
            payload.model_dump(exclude_unset=True),
        )
    except MCPClientError as exc:
        raise _http_error(exc) from exc


@router.post("/servers/{server_id}/enable")
async def enable_mcp_server(
    server_id: str,
    request: Request,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> dict[str, Any]:
    try:
        return await _service(request, session, owner.user.id).set_enabled(server_id, enabled=True)
    except MCPClientError as exc:
        raise _http_error(exc) from exc


@router.post("/servers/{server_id}/disable")
async def disable_mcp_server(
    server_id: str,
    request: Request,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> dict[str, Any]:
    try:
        return await _service(request, session, owner.user.id).set_enabled(server_id, enabled=False)
    except MCPClientError as exc:
        raise _http_error(exc) from exc


@router.delete("/servers/{server_id}", status_code=204)
async def delete_mcp_server(
    server_id: str,
    payload: DeleteMCPServerRequest,
    request: Request,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> Response:
    service = _service(request, session, owner.user.id)
    try:
        server = await service.get_server(server_id)
        if payload.confirm_name != server["name"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Server name confirmation does not match.",
            )
        await service.delete_server(server_id)
    except MCPClientError as exc:
        raise _http_error(exc) from exc
    return Response(status_code=204)


@router.post("/servers/{server_id}/test-connection")
async def test_mcp_connection(
    server_id: str,
    request: Request,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> dict[str, Any]:
    try:
        return await _service(request, session, owner.user.id).test_connection(server_id)
    except MCPClientError as exc:
        raise _http_error(exc) from exc


@router.post("/servers/{server_id}/refresh-capabilities")
async def refresh_mcp_capabilities(
    server_id: str,
    request: Request,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> dict[str, Any]:
    try:
        return await _service(request, session, owner.user.id).refresh_capabilities(server_id)
    except MCPClientError as exc:
        raise _http_error(exc) from exc


@router.patch("/capabilities/{capability_id}/policy")
async def update_mcp_capability_policy(
    capability_id: str,
    payload: CapabilityPolicyRequest,
    request: Request,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> dict[str, Any]:
    try:
        return await _service(request, session, owner.user.id).update_capability_policy(
            capability_id,
            enabled=payload.enabled,
            risk_class=payload.risk_class,
            approval_policy=payload.approval_policy,
            expected_side_effects=payload.expected_side_effects,
            confirm_broadening=payload.confirm_broadening,
        )
    except MCPClientError as exc:
        raise _http_error(exc) from exc


@router.post("/servers/{server_id}/capabilities/{capability_id}/invoke", status_code=202)
async def invoke_mcp_tool_via_agent(
    server_id: str,
    capability_id: str,
    payload: InvokeMCPToolRequest,
    request: Request,
    session: DbSession,
    owner: CsrfOwnerContext,
    idempotency_key: Annotated[str | None, Header(alias="idempotency-key")] = None,
) -> dict[str, Any]:
    service = _service(request, session, owner.user.id)
    try:
        capability = await service.get_tool_capability(server_id, capability_id)
    except MCPClientError as exc:
        raise _http_error(exc) from exc
    tool_id = canonical_mcp_tool_id(server_id, capability.name)
    owner_request = payload.owner_request or (
        f"Use MCP tool {capability.name} with arguments "
        f"{json.dumps(payload.arguments, sort_keys=True)}"
    )
    return await AgentRuntimeService(
        session=session, settings=get_settings_from_app(request)
    ).start(
        AgentRunRequest(
            owner_user_id=owner.user.id,
            owner_request=owner_request,
            request_id=str(getattr(request.state, "request_id", "")),
            trace_id=str(getattr(request.state, "trace_id", "")),
            idempotency_key=idempotency_key,
            allowed_tools=(tool_id,),
            limits=AgentRunLimits(
                max_steps=payload.max_steps, max_tool_calls=payload.max_tool_calls
            ),
        )
    )


@router.get("/audit")
async def list_mcp_audit(
    request: Request,
    session: DbSession,
    owner: OwnerContext,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    return await _service(request, session, owner.user.id).list_audit(limit=limit, offset=offset)


def _service(request: Request, session: DbSession, owner_user_id: str) -> MCPRegistryService:
    settings = get_settings_from_app(request)
    if not settings.mcp_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MCP is disabled.",
        )
    return MCPRegistryService(
        session=session,
        settings=settings,
        owner_user_id=owner_user_id,
        request_id=str(getattr(request.state, "request_id", "")),
        trace_id=str(getattr(request.state, "trace_id", "")),
    )


def _http_error(exc: MCPClientError) -> HTTPException:
    status_code = 422
    if exc.code.endswith("not_found"):
        status_code = status.HTTP_404_NOT_FOUND
    elif exc.code in {
        "server_disabled",
        "policy_broadening_requires_confirmation",
        "mcp_tool_not_allowed",
    }:
        status_code = status.HTTP_409_CONFLICT
    elif exc.code in {"mcp_timeout", "remote_mcp_unreachable", "remote_mcp_http_error"}:
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HTTPException(status_code=status_code, detail=exc.detail)
