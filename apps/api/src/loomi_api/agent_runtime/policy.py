from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from loomi_api.agent_runtime.contracts import Tool

POLICY_VERSION = "phase4-v1"
REDACTED = "[redacted]"
SECRET_KEY_PARTS = (
    "secret",
    "token",
    "password",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
)
SAFE_TOKEN_METRIC_KEYS = {
    "completion_tokens",
    "input_tokens",
    "max_tokens",
    "output_tokens",
    "prompt_tokens",
    "token_budget",
    "token_usage",
    "tokens",
    "total_tokens",
}
INLINE_SECRET_RE = re.compile(
    r"(?i)\b(api[_-]?key|token|password|authorization|secret)\s*[:=]\s*([^\s,;]+)"
)


class PolicyError(ValueError):
    """Raised when a tool request violates runtime policy."""


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def canonical_args_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def sanitize_value(value: Any, *, string_limit: int = 1200, depth: int = 0) -> Any:
    if depth > 8:
        return "[truncated-depth]"
    if isinstance(value, str):
        collapsed = INLINE_SECRET_RE.sub(
            lambda match: f"{match.group(1)}={REDACTED}",
            value,
        )
        collapsed = " ".join(collapsed.split())
        if len(collapsed) > string_limit:
            return f"{collapsed[: string_limit - 1].rstrip()}..."
        return collapsed
    if isinstance(value, int | float | bool) or value is None:
        return value
    if isinstance(value, list | tuple):
        limited = list(value[:50])
        list_output = [
            sanitize_value(item, string_limit=string_limit, depth=depth + 1)
            for item in limited
        ]
        if len(value) > len(limited):
            list_output.append("[truncated-list]")
        return list_output
    if isinstance(value, dict):
        dict_output: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 80:
                dict_output["truncated"] = True
                break
            key_text = str(key)
            if _looks_secret_key(key_text):
                dict_output[key_text] = REDACTED
            else:
                dict_output[key_text] = sanitize_value(
                    item,
                    string_limit=string_limit,
                    depth=depth + 1,
                )
        return dict_output
    return str(value)


def truncate_json_payload(payload: dict[str, Any], *, max_bytes: int) -> dict[str, Any]:
    sanitized = sanitize_value(payload)
    encoded = json.dumps(sanitized, sort_keys=True, default=str)
    if len(encoded.encode("utf-8")) <= max_bytes:
        return sanitized if isinstance(sanitized, dict) else {"value": sanitized}
    return {
        "truncated": True,
        "sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        "preview": encoded[: max(80, min(max_bytes, 1200))],
    }


def validate_tool_args(tool: Tool, arguments: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        raise PolicyError("Tool arguments must be an object.")
    schema = tool.input_schema
    if schema.get("type") != "object":
        raise PolicyError("Only object tool schemas are supported.")
    required = set(_as_str_list(schema.get("required", [])))
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        raise PolicyError("Tool schema properties must be an object.")
    validated: dict[str, Any] = {}
    for name in required:
        if name not in arguments:
            raise PolicyError(f"Missing required argument: {name}")
    additional = bool(schema.get("additionalProperties", False))
    for name, value in arguments.items():
        field_schema = properties.get(name)
        if field_schema is None:
            if additional:
                validated[name] = value
                continue
            raise PolicyError(f"Unknown argument: {name}")
        if not isinstance(field_schema, dict):
            raise PolicyError(f"Invalid schema for argument: {name}")
        validated[name] = _validate_field(name, value, field_schema)
    return validated


def approval_required(tool: Tool) -> bool:
    return tool.approval_policy == "always" or tool.risk_class != "read-only"


def policy_decision(
    tool: Tool,
    allowed_tools: tuple[str, ...],
    arguments_hash: str,
) -> dict[str, Any]:
    allowed = tool.id in allowed_tools
    requires_approval = approval_required(tool)
    return {
        "policy_version": POLICY_VERSION,
        "tool_id": tool.id,
        "allowed": allowed,
        "requires_approval": requires_approval,
        "risk_class": tool.risk_class,
        "arguments_hash": arguments_hash,
    }


def forbidden_tool_request(owner_request: str) -> bool:
    text = owner_request.casefold()
    phrases = (
        "run shell",
        "execute shell",
        "use bash",
        "use python",
        "execute python",
        "raw sql",
        "send email",
        "unrestricted http",
        "delete file",
        "read /etc",
        "reveal api key",
        "show api key",
        "ignore policy and",
    )
    return any(phrase in text for phrase in phrases)


def _validate_field(name: str, value: Any, schema: dict[str, Any]) -> Any:
    expected = schema.get("type")
    if expected == "string":
        if not isinstance(value, str):
            raise PolicyError(f"{name} must be a string.")
        min_length = schema.get("minLength")
        max_length = schema.get("maxLength")
        if isinstance(min_length, int) and len(value) < min_length:
            raise PolicyError(f"{name} is too short.")
        if isinstance(max_length, int) and len(value) > max_length:
            raise PolicyError(f"{name} is too long.")
        enum = schema.get("enum")
        if isinstance(enum, list) and value not in enum:
            raise PolicyError(f"{name} must be one of the allowed values.")
        return value
    if expected == "integer":
        if not isinstance(value, int):
            raise PolicyError(f"{name} must be an integer.")
        return _validate_number(name, value, schema)
    if expected == "number":
        if not isinstance(value, int | float):
            raise PolicyError(f"{name} must be a number.")
        return _validate_number(name, float(value), schema)
    if expected == "boolean":
        if not isinstance(value, bool):
            raise PolicyError(f"{name} must be a boolean.")
        return value
    if expected == "array":
        if not isinstance(value, list):
            raise PolicyError(f"{name} must be an array.")
        max_items = schema.get("maxItems")
        if isinstance(max_items, int) and len(value) > max_items:
            raise PolicyError(f"{name} has too many items.")
        return value
    if expected == "object":
        if not isinstance(value, dict):
            raise PolicyError(f"{name} must be an object.")
        return value
    raise PolicyError(f"Unsupported schema type for {name}.")


def _validate_number(name: str, value: int | float, schema: dict[str, Any]) -> int | float:
    minimum = schema.get("minimum")
    maximum = schema.get("maximum")
    if isinstance(minimum, int | float) and value < minimum:
        raise PolicyError(f"{name} is below the minimum.")
    if isinstance(maximum, int | float) and value > maximum:
        raise PolicyError(f"{name} is above the maximum.")
    return value


def _as_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _looks_secret_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    if normalized in SAFE_TOKEN_METRIC_KEYS:
        return False
    return any(part in normalized for part in SECRET_KEY_PARTS)
