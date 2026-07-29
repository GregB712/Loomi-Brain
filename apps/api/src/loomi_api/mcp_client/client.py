from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast

from loomi_api.agent_runtime.policy import truncate_json_payload
from loomi_api.config import Settings
from loomi_api.db.models import MCPServer
from loomi_api.mcp_client.protocol import (
    MCPClientError,
    bounded_text,
    normalize_output_schema,
    normalize_tool_schema,
    sanitize_metadata,
    schema_hash,
)
from loomi_api.mcp_client.transports import open_transport


@dataclass(frozen=True)
class DiscoveredCapability:
    capability_type: str
    name: str
    title: str | None
    description: str | None
    schema: dict[str, Any]
    output_schema: dict[str, Any]
    schema_hash: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class DiscoveryResult:
    server_info: dict[str, Any]
    instructions: str | None
    supported_versions: list[str]
    capabilities: list[DiscoveredCapability]
    raw_counts: dict[str, int]


async def discover_capabilities(settings: Settings, server: MCPServer) -> DiscoveryResult:
    async with open_transport(settings, server) as transport:
        discover_response = await transport.request("server/discover")
        discover = discover_response.result
        tools = await _optional_request(transport, "tools/list")
        resources = await _optional_request(transport, "resources/list")
        prompts = await _optional_request(transport, "prompts/list")

    capabilities: list[DiscoveredCapability] = []
    for item in _as_list(tools.get("tools")):
        capabilities.append(_tool_capability(item))
    for item in _as_list(resources.get("resources")):
        capabilities.append(_display_capability("resource", item, "uri"))
    for item in _as_list(prompts.get("prompts")):
        capabilities.append(_display_capability("prompt", item, "name"))

    return DiscoveryResult(
        server_info=_safe_dict(discover.get("serverInfo") or discover.get("_meta", {})),
        instructions=bounded_text(discover.get("instructions"), limit=500)
        if discover.get("instructions")
        else None,
        supported_versions=[str(item) for item in _as_list(discover.get("supportedVersions"))],
        capabilities=capabilities,
        raw_counts={
            "tools": len(_as_list(tools.get("tools"))),
            "resources": len(_as_list(resources.get("resources"))),
            "prompts": len(_as_list(prompts.get("prompts"))),
        },
    )


async def call_tool(
    settings: Settings,
    server: MCPServer,
    *,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    async with open_transport(settings, server) as transport:
        result = await transport.request(
            "tools/call",
            {"name": tool_name, "arguments": arguments},
            name=tool_name,
        )
    return sanitize_tool_result(result.result, max_bytes=server.output_size_limit)


def sanitize_tool_result(result: dict[str, Any], *, max_bytes: int) -> dict[str, Any]:
    structured = result.get("structuredContent")
    content = result.get("content")
    output = {
        "result_type": bounded_text(result.get("resultType") or "complete", limit=80),
        "is_error": bool(result.get("isError", False)),
        "structured_content": sanitize_metadata(structured, string_limit=800),
        "content": _sanitize_content(content),
    }
    return truncate_json_payload(output, max_bytes=max_bytes)


async def _optional_request(transport: Any, method: str) -> dict[str, Any]:
    try:
        response = await transport.request(method)
        return cast(dict[str, Any], response.result)
    except MCPClientError as exc:
        if str(exc.code) in {"-32601", "method_not_found", "mcp_method_not_found"}:
            return {}
        return {}


def _tool_capability(item: object) -> DiscoveredCapability:
    if not isinstance(item, dict):
        raise MCPClientError("malformed_capability", "MCP tool capability must be an object.")
    name = bounded_text(item.get("name"), limit=128)
    schema = normalize_tool_schema(item.get("inputSchema"))
    output_schema = normalize_output_schema(item.get("outputSchema"))
    metadata = _safe_dict(
        {
            "annotations": item.get("annotations")
            if isinstance(item.get("annotations"), dict)
            else {},
            "icons": item.get("icons") if isinstance(item.get("icons"), list) else [],
        }
    )
    metadata["source"] = "mcp_discovery"
    return DiscoveredCapability(
        capability_type="tool",
        name=name,
        title=bounded_text(item.get("title"), limit=160) if item.get("title") else None,
        description=(
            bounded_text(item.get("description"), limit=500) if item.get("description") else None
        ),
        schema=schema,
        output_schema=output_schema,
        schema_hash=schema_hash({"input": schema, "output": output_schema}),
        metadata=metadata,
    )


def _display_capability(kind: str, item: object, key: str) -> DiscoveredCapability:
    if not isinstance(item, dict):
        raise MCPClientError("malformed_capability", "MCP capability must be an object.")
    name = bounded_text(item.get(key) or item.get("name"), limit=160)
    schema = {"type": "object", "additionalProperties": False, "properties": {}, "required": []}
    return DiscoveredCapability(
        capability_type=kind,
        name=name,
        title=bounded_text(item.get("title") or item.get("name"), limit=160)
        if item.get("title") or item.get("name")
        else None,
        description=(
            bounded_text(item.get("description"), limit=500) if item.get("description") else None
        ),
        schema=schema,
        output_schema={},
        schema_hash=schema_hash({"display": kind, "name": name}),
        metadata=_safe_dict(item),
    )


def _sanitize_content(value: object) -> list[dict[str, Any]]:
    items = _as_list(value)[:20]
    output: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        kind = bounded_text(item.get("type") or "unknown", limit=40)
        if kind == "text":
            output.append({"type": "text", "text": bounded_text(item.get("text"), limit=1000)})
        else:
            output.append({"type": kind, "metadata": sanitize_metadata(item, string_limit=240)})
    return output


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_dict(value: object) -> dict[str, Any]:
    sanitized = sanitize_metadata(value, string_limit=300)
    if not isinstance(sanitized, dict):
        return {}
    return cast(dict[str, Any], json.loads(json.dumps(sanitized, default=str)))
