from __future__ import annotations

from typing import Any, cast

from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from loomi_api.agent_runtime.policy import sanitize_value
from loomi_api.config import Settings
from loomi_api.db.base import utc_now
from loomi_api.db.models import AuditEvent, MCPCapability, MCPServer
from loomi_api.mcp_client.client import call_tool, discover_capabilities
from loomi_api.mcp_client.protocol import (
    MCPClientError,
    canonical_mcp_tool_id,
    risk_from_value,
    sanitize_metadata,
)
from loomi_api.mcp_client.security import (
    sanitized_server_config,
    validate_remote_endpoint,
    validate_secret_ref,
    validate_template_name,
    validate_working_directory,
)
from loomi_api.mcp_client.templates import available_stdio_templates, resolve_stdio_template
from loomi_api.observability.telemetry import elapsed_ms, record_span, start_timer


class MCPRegistryService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: Settings,
        owner_user_id: str,
        request_id: str,
        trace_id: str,
    ) -> None:
        self.session = session
        self.settings = settings
        self.owner_user_id = owner_user_id
        self.request_id = request_id
        self.trace_id = trace_id

    async def list_servers(self, *, limit: int, offset: int) -> dict[str, Any]:
        total = int(
            await self.session.scalar(
                select(func.count(MCPServer.id)).where(
                    MCPServer.owner_user_id == self.owner_user_id
                )
            )
            or 0
        )
        rows = list(
            await self.session.scalars(
                select(MCPServer)
                .where(MCPServer.owner_user_id == self.owner_user_id)
                .order_by(desc(MCPServer.created_at))
                .offset(offset)
                .limit(limit)
            )
        )
        return {
            "items": [await self.serialize_server(row) for row in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
            "templates": available_stdio_templates(),
        }

    async def get_server(self, server_id: str) -> dict[str, Any]:
        server = await self._load_server(server_id)
        return await self.serialize_server(server, include_capabilities=True)

    async def create_server(self, payload: dict[str, Any]) -> dict[str, Any]:
        transport = str(payload.get("transport") or "")
        if transport not in {"stdio", "streamable_http"}:
            raise MCPClientError("invalid_transport", "Unsupported MCP transport.")
        command_template: list[str] | None = None
        url: str | None = None
        if transport == "stdio":
            template_name = validate_template_name(str(payload.get("template_name") or ""))
            resolve_stdio_template([template_name])
            command_template = [template_name]
        else:
            allow_private = bool(payload.get("allow_private_networks", False))
            url = validate_remote_endpoint(
                self.settings,
                str(payload.get("url") or ""),
                allow_private_networks=allow_private,
            )
        working_directory = validate_working_directory(
            self.settings,
            cast(str | None, payload.get("working_directory")),
        )
        server = MCPServer(
            owner_user_id=self.owner_user_id,
            name=str(payload["name"]),
            description=cast(str | None, payload.get("description")),
            transport=transport,
            command_template=command_template,
            url=url,
            secret_ref=validate_secret_ref(cast(str | None, payload.get("secret_ref"))),
            environment_allowlist=[
                str(item)[:120]
                for item in cast(list[Any], payload.get("environment_allowlist", []))
            ][:20],
            working_directory=working_directory,
            connection_timeout_seconds=int(
                payload.get(
                    "connection_timeout_seconds",
                    self.settings.mcp_default_connection_timeout_seconds,
                )
            ),
            tool_timeout_seconds=int(
                payload.get("tool_timeout_seconds", self.settings.mcp_default_tool_timeout_seconds)
            ),
            output_size_limit=int(
                payload.get("output_size_limit", self.settings.mcp_default_output_size_limit)
            ),
            health_status="unknown",
            capability_cache={},
            policy={
                "deny_by_default": True,
                "allow_private_networks": bool(payload.get("allow_private_networks", False)),
            },
        )
        self.session.add(server)
        await self.session.flush()
        await self._audit("mcp.server_created", server, {"transport": transport})
        await self._span(
            "loomi.mcp.registry",
            {"action": "create", "server_id": server.id, "transport": transport},
        )
        await self.session.commit()
        return await self.serialize_server(server)

    async def update_server(self, server_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        server = await self._load_server(server_id)
        if "name" in payload and payload["name"]:
            server.name = str(payload["name"])
        if "description" in payload:
            server.description = cast(str | None, payload.get("description"))
        if "secret_ref" in payload:
            server.secret_ref = validate_secret_ref(cast(str | None, payload.get("secret_ref")))
        if "environment_allowlist" in payload:
            server.environment_allowlist = [
                str(item)[:120]
                for item in cast(list[Any], payload.get("environment_allowlist") or [])
            ][:20]
        for key in ("connection_timeout_seconds", "tool_timeout_seconds", "output_size_limit"):
            if key in payload and payload[key] is not None:
                setattr(server, key, int(payload[key]))
        if "allow_private_networks" in payload:
            server.policy = {
                **(server.policy or {}),
                "allow_private_networks": bool(payload["allow_private_networks"]),
            }
            if server.url:
                validate_remote_endpoint(
                    self.settings,
                    server.url,
                    allow_private_networks=bool(payload["allow_private_networks"]),
                )
        await self._audit("mcp.server_updated", server, {"fields": sorted(payload)})
        await self._span("loomi.mcp.registry", {"action": "update", "server_id": server.id})
        await self.session.commit()
        return await self.serialize_server(server)

    async def set_enabled(self, server_id: str, *, enabled: bool) -> dict[str, Any]:
        server = await self._load_server(server_id)
        server.disabled_at = None if enabled else utc_now()
        await self._audit(
            "mcp.server_enabled" if enabled else "mcp.server_disabled",
            server,
            {"enabled": enabled},
        )
        await self._span(
            "loomi.mcp.registry",
            {"action": "enable" if enabled else "disable", "server_id": server.id},
        )
        await self.session.commit()
        return await self.serialize_server(server)

    async def delete_server(self, server_id: str) -> None:
        server = await self._load_server(server_id)
        await self._audit("mcp.server_deleted", server, {"server_name": server.name})
        await self.session.execute(
            delete(MCPCapability).where(MCPCapability.server_id == server.id)
        )
        await self.session.delete(server)
        await self._span("loomi.mcp.registry", {"action": "delete", "server_id": server_id})
        await self.session.commit()

    async def test_connection(self, server_id: str) -> dict[str, Any]:
        server = await self._load_server(server_id)
        started = start_timer()
        try:
            discovery = await discover_capabilities(self.settings, server)
            server.health_status = "connected"
            server.health_detail = "Connection test succeeded."
            server.last_connected_at = utc_now()
            server.last_error = None
            status = "ok"
            error_code = None
            payload = {
                "ok": True,
                "server_info": discovery.server_info,
                "supported_versions": discovery.supported_versions,
                "raw_counts": discovery.raw_counts,
            }
        except MCPClientError as exc:
            server.health_status = "failed"
            server.health_detail = exc.detail
            server.last_error = {"code": exc.code, "detail": exc.detail}
            status = "error"
            error_code = exc.code
            payload = {"ok": False, "code": exc.code, "detail": exc.detail}
        await self._audit("mcp.connection_tested", server, payload)
        await self._span(
            "loomi.mcp.connection",
            {"server_id": server.id, "status": status, "duration_ms": elapsed_ms(started)},
            status=status,
            error_code=error_code,
            duration_ms=elapsed_ms(started),
        )
        await self.session.commit()
        return payload

    async def refresh_capabilities(self, server_id: str) -> dict[str, Any]:
        server = await self._load_server(server_id)
        if server.disabled_at is not None:
            raise MCPClientError("server_disabled", "MCP server is disabled.")
        started = start_timer()
        try:
            discovery = await discover_capabilities(self.settings, server)
        except MCPClientError as exc:
            server.health_status = "failed"
            server.health_detail = exc.detail
            server.last_error = {"code": exc.code, "detail": exc.detail}
            await self._audit(
                "mcp.capability_refresh_failed",
                server,
                {"code": exc.code, "detail": exc.detail},
            )
            await self._span(
                "loomi.mcp.discovery",
                {"server_id": server.id, "status": "error"},
                status="error",
                error_code=exc.code,
                duration_ms=elapsed_ms(started),
            )
            await self.session.commit()
            raise

        existing = {
            (cap.capability_type, cap.name): cap
            for cap in await self._capabilities(server.id, include_disabled=True)
        }
        seen: set[tuple[str, str]] = set()
        for item in discovery.capabilities:
            key = (item.capability_type, item.name)
            seen.add(key)
            cap = existing.get(key)
            if cap is None:
                cap = MCPCapability(
                    server_id=server.id,
                    owner_user_id=self.owner_user_id,
                    capability_type=item.capability_type,
                    name=item.name,
                    enabled=False,
                    risk_class="credential-sensitive"
                    if item.capability_type == "tool"
                    else "read-only",
                    approval_policy="risk-based",
                )
                self.session.add(cap)
            elif cap.schema_hash and cap.schema_hash != item.schema_hash:
                cap.enabled = False
                cap.risk_class = "credential-sensitive"
                cap.approval_policy = "risk-based"
            cap.title = item.title
            cap.description = item.description
            cap.schema = item.schema
            cap.output_schema = item.output_schema
            cap.schema_hash = item.schema_hash
            cap.capability_metadata = item.metadata
            cap.last_seen_at = utc_now()
        for key, cap in existing.items():
            if key not in seen:
                cap.enabled = False
                cap.capability_metadata = {**(cap.capability_metadata or {}), "stale": True}
        server.health_status = "connected"
        server.health_detail = "Capabilities refreshed."
        server.last_connected_at = utc_now()
        server.last_capability_refresh_at = utc_now()
        server.last_error = None
        server.capability_cache = {
            "server_info": discovery.server_info,
            "instructions": discovery.instructions,
            "supported_versions": discovery.supported_versions,
            "raw_counts": discovery.raw_counts,
        }
        await self._audit(
            "mcp.capabilities_refreshed",
            server,
            {"counts": discovery.raw_counts, "capability_count": len(discovery.capabilities)},
        )
        await self._span(
            "loomi.mcp.discovery",
            {
                "server_id": server.id,
                "tool_count": discovery.raw_counts.get("tools", 0),
                "resource_count": discovery.raw_counts.get("resources", 0),
                "prompt_count": discovery.raw_counts.get("prompts", 0),
            },
            duration_ms=elapsed_ms(started),
        )
        await self.session.commit()
        return await self.serialize_server(server, include_capabilities=True)

    async def update_capability_policy(
        self,
        capability_id: str,
        *,
        enabled: bool,
        risk_class: str,
        approval_policy: str,
        expected_side_effects: str | None,
        confirm_broadening: bool,
    ) -> dict[str, Any]:
        cap = await self._load_capability(capability_id)
        server = await self._load_server(cap.server_id)
        next_risk = risk_from_value(risk_class)
        next_policy = (
            approval_policy
            if approval_policy in {"never", "risk-based", "always"}
            else "risk-based"
        )
        broadening = (
            (enabled and not cap.enabled)
            or (cap.risk_class != "read-only" and next_risk == "read-only")
            or (cap.approval_policy != "never" and next_policy == "never")
        )
        if broadening and not confirm_broadening:
            raise MCPClientError(
                "policy_broadening_requires_confirmation",
                "Policy broadening requires explicit confirmation.",
            )
        cap.enabled = enabled
        cap.risk_class = next_risk
        cap.approval_policy = next_policy
        cap.capability_metadata = {
            **(cap.capability_metadata or {}),
            "expected_side_effects": str(expected_side_effects or "")[:500],
            "policy_updated_at": utc_now().isoformat(),
        }
        await self._audit(
            "mcp.capability_policy_updated",
            server,
            {
                "capability_id": cap.id,
                "capability_type": cap.capability_type,
                "name": cap.name,
                "enabled": enabled,
                "risk_class": cap.risk_class,
                "approval_policy": cap.approval_policy,
                "schema_hash": cap.schema_hash,
            },
        )
        await self._span(
            "loomi.mcp.policy_check",
            {
                "server_id": server.id,
                "capability_id": cap.id,
                "enabled": enabled,
                "risk_class": cap.risk_class,
            },
        )
        await self.session.commit()
        return serialize_capability(cap)

    async def get_tool_capability(self, server_id: str, capability_id: str) -> MCPCapability:
        cap = await self._load_capability(capability_id)
        if cap.server_id != server_id or cap.capability_type != "tool":
            raise MCPClientError("capability_not_found", "MCP tool capability not found.")
        return cap

    async def list_audit(self, *, limit: int, offset: int) -> dict[str, Any]:
        rows = list(
            await self.session.scalars(
                select(AuditEvent)
                .where(
                    AuditEvent.owner_user_id == self.owner_user_id,
                    AuditEvent.event_type.like("mcp.%"),
                )
                .order_by(desc(AuditEvent.created_at))
                .offset(offset)
                .limit(limit)
            )
        )
        return {
            "items": [
                {
                    "id": row.id,
                    "event_type": row.event_type,
                    "request_id": row.request_id,
                    "trace_id": row.trace_id,
                    "metadata": row.event_metadata or {},
                    "created_at": row.created_at.isoformat(),
                }
                for row in rows
            ],
            "limit": limit,
            "offset": offset,
        }

    async def execute_tool(
        self,
        server: MCPServer,
        capability: MCPCapability,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        started = start_timer()
        try:
            result = await call_tool(
                self.settings,
                server,
                tool_name=capability.name,
                arguments=arguments,
            )
            await self._audit(
                "mcp.tool_executed",
                server,
                {
                    "capability_id": capability.id,
                    "tool_name": capability.name,
                    "risk_class": capability.risk_class,
                    "schema_hash": capability.schema_hash,
                    "output_truncated": bool(result.get("truncated")),
                },
            )
            await self._span(
                "loomi.mcp.execution",
                {
                    "server_id": server.id,
                    "capability_id": capability.id,
                    "tool_name": capability.name,
                    "risk_class": capability.risk_class,
                    "output_truncated": bool(result.get("truncated")),
                },
                duration_ms=elapsed_ms(started),
            )
            await self.session.flush()
            return result
        except MCPClientError as exc:
            await self._audit(
                "mcp.tool_failed",
                server,
                {
                    "capability_id": capability.id,
                    "tool_name": capability.name,
                    "code": exc.code,
                },
            )
            await self._span(
                "loomi.mcp.execution",
                {
                    "server_id": server.id,
                    "capability_id": capability.id,
                    "tool_name": capability.name,
                },
                status="error",
                error_code=exc.code,
                duration_ms=elapsed_ms(started),
            )
            raise

    async def serialize_server(
        self,
        server: MCPServer,
        *,
        include_capabilities: bool = False,
    ) -> dict[str, Any]:
        payload = serialize_server(server)
        if include_capabilities:
            payload["capabilities"] = [
                serialize_capability(cap)
                for cap in await self._capabilities(server.id, include_disabled=True)
            ]
        return payload

    async def _load_server(self, server_id: str) -> MCPServer:
        server = await self.session.scalar(
            select(MCPServer).where(
                MCPServer.id == server_id,
                MCPServer.owner_user_id == self.owner_user_id,
            )
        )
        if server is None:
            raise MCPClientError("server_not_found", "MCP server not found.")
        return server

    async def _load_capability(self, capability_id: str) -> MCPCapability:
        cap = await self.session.scalar(
            select(MCPCapability).where(
                MCPCapability.id == capability_id,
                MCPCapability.owner_user_id == self.owner_user_id,
            )
        )
        if cap is None:
            raise MCPClientError("capability_not_found", "MCP capability not found.")
        return cap

    async def _capabilities(
        self,
        server_id: str,
        *,
        include_disabled: bool,
    ) -> list[MCPCapability]:
        stmt = select(MCPCapability).where(
            MCPCapability.server_id == server_id,
            MCPCapability.owner_user_id == self.owner_user_id,
        )
        if not include_disabled:
            stmt = stmt.where(MCPCapability.enabled.is_(True))
        return list(
            await self.session.scalars(
                stmt.order_by(MCPCapability.capability_type, MCPCapability.name)
            )
        )

    async def _audit(self, event_type: str, server: MCPServer, metadata: dict[str, Any]) -> None:
        self.session.add(
            AuditEvent(
                owner_user_id=self.owner_user_id,
                event_type=event_type,
                request_id=self.request_id,
                trace_id=self.trace_id,
                event_metadata=cast(
                    dict[str, Any],
                    sanitize_value(
                        {
                            "server_id": server.id,
                            "server_name": server.name,
                            **sanitized_server_config(metadata),
                        }
                    ),
                ),
            )
        )

    async def _span(
        self,
        name: str,
        attributes: dict[str, Any],
        *,
        status: str = "ok",
        error_code: str | None = None,
        duration_ms: int = 0,
    ) -> None:
        await record_span(
            self.session,
            self.settings,
            name=name,
            component="mcp",
            trace_id=self.trace_id,
            owner_user_id=self.owner_user_id,
            status=status,
            duration_ms=duration_ms,
            error_code=error_code,
            attributes=attributes,
        )


def serialize_server(server: MCPServer) -> dict[str, Any]:
    return {
        "id": server.id,
        "name": server.name,
        "description": server.description,
        "transport": server.transport,
        "enabled": server.disabled_at is None,
        "command_template": list(server.command_template or []),
        "url": server.url,
        "has_secret_ref": bool(server.secret_ref),
        "environment_allowlist": list(server.environment_allowlist or []),
        "working_directory": server.working_directory,
        "connection_timeout_seconds": server.connection_timeout_seconds,
        "tool_timeout_seconds": server.tool_timeout_seconds,
        "output_size_limit": server.output_size_limit,
        "health_status": server.health_status,
        "health_detail": server.health_detail,
        "capability_cache": sanitize_metadata(server.capability_cache or {}),
        "policy": sanitize_metadata(server.policy or {}),
        "last_connected_at": (
            server.last_connected_at.isoformat() if server.last_connected_at else None
        ),
        "last_capability_refresh_at": (
            server.last_capability_refresh_at.isoformat()
            if server.last_capability_refresh_at
            else None
        ),
        "last_error": sanitize_metadata(server.last_error or {}),
        "created_at": server.created_at.isoformat(),
        "updated_at": server.updated_at.isoformat(),
    }


def serialize_capability(capability: MCPCapability) -> dict[str, Any]:
    tool_id = (
        canonical_mcp_tool_id(capability.server_id, capability.name)
        if capability.capability_type == "tool"
        else None
    )
    return {
        "id": capability.id,
        "server_id": capability.server_id,
        "tool_id": tool_id,
        "capability_type": capability.capability_type,
        "name": capability.name,
        "title": capability.title,
        "description": capability.description,
        "schema": sanitize_metadata(capability.schema or {}),
        "output_schema": sanitize_metadata(capability.output_schema or {}),
        "risk_class": capability.risk_class,
        "approval_policy": capability.approval_policy,
        "enabled": capability.enabled,
        "schema_hash": capability.schema_hash,
        "metadata": sanitize_metadata(capability.capability_metadata or {}),
        "last_seen_at": capability.last_seen_at.isoformat() if capability.last_seen_at else None,
        "created_at": capability.created_at.isoformat(),
        "updated_at": capability.updated_at.isoformat(),
    }
