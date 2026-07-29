from __future__ import annotations

import base64
import hashlib
import json
import re
from typing import Any, cast

from loomi_api.agent_runtime.contracts import ToolRisk
from loomi_api.agent_runtime.policy import sanitize_value

MCP_PROTOCOL_VERSION = "2026-07-28"
MCP_TOOL_ID_PREFIX = "mcp::"
CLIENT_INFO = {"name": "loomi-brain", "version": "0.1.0"}
SAFE_TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
SAFE_TEMPLATE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")

RISK_CLASSES: tuple[ToolRisk, ...] = (
    "read-only",
    "local-mutation",
    "external-mutation",
    "credential-sensitive",
    "destructive",
)
APPROVAL_POLICIES = {"never", "risk-based", "always"}


class MCPClientError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def canonical_mcp_tool_id(server_id: str, tool_name: str) -> str:
    if not SAFE_TOOL_NAME_RE.fullmatch(tool_name):
        raise MCPClientError("invalid_tool_name", "MCP tool names must be header-safe ASCII.")
    return f"{MCP_TOOL_ID_PREFIX}{server_id}::{tool_name}"


def parse_mcp_tool_id(tool_id: str) -> tuple[str, str]:
    if not tool_id.startswith(MCP_TOOL_ID_PREFIX):
        raise MCPClientError("invalid_tool_id", "MCP tool id is not a Loomi MCP tool id.")
    remainder = tool_id[len(MCP_TOOL_ID_PREFIX) :]
    server_id, separator, tool_name = remainder.partition("::")
    if not separator or not server_id or not SAFE_TOOL_NAME_RE.fullmatch(tool_name):
        raise MCPClientError("invalid_tool_id", "MCP tool id is malformed.")
    return (server_id, tool_name)


def request_payload(method: str, params: dict[str, Any] | None, request_id: int) -> dict[str, Any]:
    payload_params = dict(params or {})
    payload_params["_meta"] = {
        "io.modelcontextprotocol/protocolVersion": MCP_PROTOCOL_VERSION,
        "io.modelcontextprotocol/clientInfo": CLIENT_INFO,
        "io.modelcontextprotocol/clientCapabilities": {},
    }
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": payload_params,
    }


def mcp_headers(method: str, name: str | None = None) -> dict[str, str]:
    headers = {
        "content-type": "application/json",
        "accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
        "Mcp-Method": method,
    }
    if name is not None:
        headers["Mcp-Name"] = safe_header_value(name)
    return headers


def safe_header_value(value: str) -> str:
    if (
        value.strip() == value
        and not value.startswith("=?base64?")
        and not value.endswith("?=")
        and all(char == "\t" or char == " " or "\x21" <= char <= "\x7e" for char in value)
    ):
        return value
    encoded = base64.b64encode(value.encode("utf-8")).decode("ascii")
    return f"=?base64?{encoded}?="


def schema_hash(schema: dict[str, Any]) -> str:
    encoded = json.dumps(schema, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def sanitize_metadata(value: Any, *, string_limit: int = 500) -> Any:
    sanitized = sanitize_value(value, string_limit=string_limit)
    return json.loads(json.dumps(sanitized, default=str))


def bounded_text(value: object, *, limit: int = 500) -> str:
    text = str(value or "")
    safe = sanitize_value(text, string_limit=limit)
    return str(safe)


def normalize_tool_schema(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"type": "object", "additionalProperties": False, "properties": {}}
    schema = sanitize_metadata(value, string_limit=240)
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise MCPClientError("unsupported_schema", "MCP tool schemas must be JSON objects.")
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        raise MCPClientError("unsupported_schema", "MCP tool schema properties must be an object.")
    clean_properties: dict[str, Any] = {}
    for raw_name, raw_field in properties.items():
        name = str(raw_name)
        if not SAFE_TOOL_NAME_RE.fullmatch(name):
            raise MCPClientError(
                "unsupported_schema", "MCP tool argument names must be safe ASCII."
            )
        if not isinstance(raw_field, dict):
            raise MCPClientError("unsupported_schema", "MCP tool argument schema is malformed.")
        expected = raw_field.get("type")
        if expected not in {"string", "integer", "number", "boolean", "array", "object"}:
            raise MCPClientError("unsupported_schema", "MCP tool argument type is unsupported.")
        field: dict[str, Any] = {"type": expected}
        for key in ("minLength", "maxLength", "minimum", "maximum", "enum", "maxItems"):
            if key in raw_field:
                field[key] = raw_field[key]
        if "description" in raw_field:
            field["description"] = bounded_text(raw_field["description"], limit=240)
        if "x-mcp-header" in raw_field:
            header_name = str(raw_field["x-mcp-header"])
            if not header_name or "\r" in header_name or "\n" in header_name:
                raise MCPClientError("unsupported_schema", "MCP header annotations are malformed.")
            field["x-mcp-header"] = header_name
        clean_properties[name] = field
    required = schema.get("required", [])
    if not isinstance(required, list) or any(
        str(item) not in clean_properties for item in required
    ):
        raise MCPClientError("unsupported_schema", "MCP tool required arguments are malformed.")
    return {
        "type": "object",
        "additionalProperties": bool(schema.get("additionalProperties", False)),
        "properties": clean_properties,
        "required": [str(item) for item in required],
    }


def normalize_output_schema(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return cast(dict[str, Any], sanitize_metadata(value, string_limit=240))


def risk_from_value(value: object) -> ToolRisk:
    text = str(value or "credential-sensitive")
    if text in RISK_CLASSES:
        return text
    return "credential-sensitive"


def approval_policy_from_value(value: object, risk_class: ToolRisk) -> str:
    text = str(value or "risk-based")
    if text in APPROVAL_POLICIES:
        return text
    return "never" if risk_class == "read-only" else "risk-based"
