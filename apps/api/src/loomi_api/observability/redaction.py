from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qsl, urlencode

REDACTED = "[redacted]"

SAFE_ATTRIBUTE_KEYS = {
    "allowed",
    "approval_id",
    "arguments_hash",
    "attempt",
    "candidate_count",
    "component",
    "content_capture",
    "conversation_id",
    "cost_budget_usd",
    "dataset",
    "debug",
    "document_count",
    "document_id",
    "document_version_id",
    "duration_ms",
    "embedding_count",
    "error_code",
    "estimated_cost_usd",
    "event_type",
    "exporter",
    "from_state",
    "input_tokens",
    "job_id",
    "kind",
    "latency_ms",
    "limit",
    "max_steps",
    "max_tool_calls",
    "message_id",
    "method",
    "min_score",
    "mode",
    "model",
    "offset",
    "operation",
    "output_tokens",
    "owner_user_id",
    "parent_span_id",
    "path",
    "policy_version",
    "prompt_id",
    "prompt_version",
    "provider",
    "query_length",
    "request_id",
    "requires_approval",
    "retention_days",
    "risk_class",
    "run_id",
    "sample_rate",
    "sampled",
    "selected_context_count",
    "span_id",
    "stage",
    "state",
    "status",
    "status_code",
    "to_state",
    "tool_call_count",
    "tool_call_id",
    "tool_id",
    "tool_name",
    "total",
    "total_tokens",
    "trace_id",
    "warning_count",
}

SECRET_KEY_PARTS = (
    "authorization",
    "cookie",
    "csrf",
    "credential",
    "key",
    "password",
    "secret",
    "session",
    "signature",
    "signed",
    "token",
)

SAFE_KEY_EXCEPTIONS = {
    "input_tokens",
    "max_tokens",
    "output_tokens",
    "token_budget",
    "total_tokens",
}

PRIVATE_KEY_LABEL = "PRIVATE " + "KEY"

SECRET_PATTERNS = (
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"(?i)\b([A-Za-z0-9_-]*(?:api[_-]?key|token|password|secret))\s*[:=]\s*([^\s,;&]+)"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bglpat-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{16,}\b"),
    re.compile(
        rf"-----BEGIN [A-Z ]*{PRIVATE_KEY_LABEL}-----.*?-----END [A-Z ]*{PRIVATE_KEY_LABEL}-----",
        re.S,
    ),
)


def redact_attributes(
    attributes: Mapping[str, Any],
    *,
    max_chars: int,
    extra_allowed: set[str] | None = None,
) -> dict[str, Any]:
    allowed = SAFE_ATTRIBUTE_KEYS | (extra_allowed or set())
    redacted: dict[str, Any] = {}
    for key, value in attributes.items():
        normalized_key = str(key)
        if normalized_key not in allowed:
            continue
        redacted[normalized_key] = redact_value(value, max_chars=max_chars)
    return redacted


def redact_headers(headers: Mapping[str, str], *, max_chars: int) -> dict[str, str]:
    safe_headers = {"content-type", "x-request-id", "x-trace-id"}
    output: dict[str, str] = {}
    for key, value in headers.items():
        normalized = key.casefold()
        if _looks_secret_key(normalized) or normalized not in safe_headers:
            output[normalized] = REDACTED
        else:
            output[normalized] = str(redact_value(value, max_chars=max_chars))
    return output


def redact_query_string(query: str, *, max_chars: int) -> str:
    pairs: list[tuple[str, str]] = []
    for key, value in parse_qsl(query, keep_blank_values=True):
        if _looks_secret_key(key):
            pairs.append((key, REDACTED))
        else:
            pairs.append((key, str(redact_value(value, max_chars=max_chars))))
    return urlencode(pairs)


def redact_value(value: Any, *, max_chars: int, depth: int = 0) -> Any:
    if depth > 8:
        return "[truncated-depth]"
    if isinstance(value, str):
        return _truncate(_redact_text(value), max_chars)
    if isinstance(value, int | float | bool) or value is None:
        return value
    if isinstance(value, list | tuple):
        list_output = [
            redact_value(item, max_chars=max_chars, depth=depth + 1) for item in value[:50]
        ]
        if len(value) > len(list_output):
            list_output.append("[truncated-list]")
        return list_output
    if isinstance(value, Mapping):
        dict_output: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 80:
                dict_output["truncated"] = True
                break
            key_text = str(key)
            if _looks_secret_key(key_text):
                dict_output[key_text] = REDACTED
            else:
                dict_output[key_text] = redact_value(item, max_chars=max_chars, depth=depth + 1)
        return dict_output
    return _truncate(_redact_text(str(value)), max_chars)


def contains_unredacted_secret(value: Any) -> bool:
    text = re.sub(
        r"(?i)\b[A-Za-z0-9_-]*(?:api[_-]?key|token|password|secret)\s*[:=]\s*['\"]?\[redacted\]['\"]?",
        "",
        str(value),
    )
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def _redact_text(value: str) -> str:
    output = value
    for pattern in SECRET_PATTERNS:
        output = pattern.sub(_replacement, output)
    return output


def _replacement(match: re.Match[str]) -> str:
    if len(match.groups()) >= 1 and match.group(1):
        return f"{match.group(1)}={REDACTED}"
    return REDACTED


def _looks_secret_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    if normalized in SAFE_KEY_EXCEPTIONS:
        return False
    return any(part in normalized for part in SECRET_KEY_PARTS)


def _truncate(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return f"{value[: max(max_chars - 1, 0)].rstrip()}..."
