from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loomi_api.agent_runtime.contracts import (
    ToolApprovalPolicy,
    ToolContext,
    ToolExecutionError,
    ToolResult,
    ToolRisk,
)
from loomi_api.config import Settings
from loomi_api.db.models import MCPCapability, MCPServer
from loomi_api.mcp_client.protocol import MCPClientError, parse_mcp_tool_id
from loomi_api.mcp_client.service import MCPRegistryService


@dataclass(frozen=True)
class MCPProxyTool:
    id: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    risk_class: ToolRisk
    timeout_seconds: int
    output_size_limit: int
    idempotent: bool
    approval_policy: ToolApprovalPolicy
    server_id: str
    tool_name: str
    schema_hash: str

    def approval_hash_payload(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "server_id": self.server_id,
            "tool_name": self.tool_name,
            "schema_hash": self.schema_hash,
            "arguments": arguments,
        }

    async def execute(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        server, capability = await load_mcp_server_and_capability(
            context.session,
            context.settings,
            context.owner_user_id,
            self.id,
        )
        service = MCPRegistryService(
            session=context.session,
            settings=context.settings,
            owner_user_id=context.owner_user_id,
            request_id=context.request_id,
            trace_id=context.trace_id,
        )
        try:
            output = await service.execute_tool(server, capability, args)
        except MCPClientError as exc:
            raise ToolExecutionError(
                exc.code, exc.detail, transient=exc.code == "mcp_timeout"
            ) from exc
        return ToolResult(
            output={
                "server_id": server.id,
                "server_name": server.name,
                "tool_name": capability.name,
                "schema_hash": capability.schema_hash,
                "untrusted_mcp_result": output,
            },
            usage={"mcp_output_truncated": bool(output.get("truncated"))},
        )


async def load_mcp_tool(
    session: AsyncSession,
    settings: Settings,
    owner_user_id: str,
    tool_id: str,
) -> MCPProxyTool | None:
    try:
        server, capability = await load_mcp_server_and_capability(
            session,
            settings,
            owner_user_id,
            tool_id,
        )
    except MCPClientError:
        return None
    return MCPProxyTool(
        id=tool_id,
        description=capability.description or f"MCP tool {capability.name}",
        input_schema=capability.schema or {},
        output_schema=capability.output_schema or {},
        risk_class=capability.risk_class,  # type: ignore[arg-type]
        timeout_seconds=server.tool_timeout_seconds or settings.mcp_default_tool_timeout_seconds,
        output_size_limit=server.output_size_limit or settings.mcp_default_output_size_limit,
        idempotent=capability.risk_class == "read-only",
        approval_policy=capability.approval_policy or "risk-based",  # type: ignore[arg-type]
        server_id=server.id,
        tool_name=capability.name,
        schema_hash=capability.schema_hash,
    )


async def load_mcp_server_and_capability(
    session: AsyncSession,
    settings: Settings,
    owner_user_id: str,
    tool_id: str,
) -> tuple[MCPServer, MCPCapability]:
    del settings
    server_id, tool_name = parse_mcp_tool_id(tool_id)
    row = (
        await session.execute(
            select(MCPServer, MCPCapability)
            .join(MCPCapability, MCPCapability.server_id == MCPServer.id)
            .where(
                MCPServer.id == server_id,
                MCPServer.owner_user_id == owner_user_id,
                MCPServer.disabled_at.is_(None),
                MCPCapability.owner_user_id == owner_user_id,
                MCPCapability.capability_type == "tool",
                MCPCapability.name == tool_name,
                MCPCapability.enabled.is_(True),
            )
        )
    ).one_or_none()
    if row is None:
        raise MCPClientError("mcp_tool_not_allowed", "MCP tool is not enabled for this owner.")
    server = row[0]
    capability = row[1]
    return (server, capability)
