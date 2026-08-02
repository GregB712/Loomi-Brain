from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

MAX_TEMPLATE_BYTES = 16_000
MAX_RENDERED_BYTES = 64_000
MAX_VARIABLES = 64

_PATH_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
_UNSAFE_TOKENS = ("{{{", "}}}", "{%", "%}", "{#", "#}", "${")
_ALLOWED_ROOTS = {"input", "retrieval", "tools", "skill"}


class TemplateSecurityError(ValueError):
    """Raised when a skill template uses unsupported or unsafe syntax."""


@dataclass(frozen=True)
class TemplateLimits:
    max_template_bytes: int = MAX_TEMPLATE_BYTES
    max_rendered_bytes: int = MAX_RENDERED_BYTES
    max_variables: int = MAX_VARIABLES


def extract_template_variables(
    template: str,
    *,
    limits: TemplateLimits | None = None,
) -> tuple[str, ...]:
    resolved_limits = limits or TemplateLimits()
    _check_template_size(template, resolved_limits)
    for token in _UNSAFE_TOKENS:
        if token in template:
            raise TemplateSecurityError(f"Unsupported template token: {token}")

    variables: list[str] = []
    index = 0
    while index < len(template):
        start = template.find("{{", index)
        stray_close = template.find("}}", index)
        if stray_close >= 0 and (start < 0 or stray_close < start):
            raise TemplateSecurityError("Template contains an unmatched closing placeholder.")
        if start < 0:
            break
        end = template.find("}}", start + 2)
        if end < 0:
            raise TemplateSecurityError("Template contains an unclosed placeholder.")
        raw_path = template[start + 2 : end].strip()
        _validate_path(raw_path)
        variables.append(raw_path)
        if len(variables) > resolved_limits.max_variables:
            raise TemplateSecurityError("Template references too many variables.")
        index = end + 2
    return tuple(dict.fromkeys(variables))


def render_template(
    template: str,
    context: dict[str, Any],
    *,
    limits: TemplateLimits | None = None,
) -> str:
    resolved_limits = limits or TemplateLimits()
    variables = extract_template_variables(template, limits=resolved_limits)
    values = {variable: _resolve_path(context, variable) for variable in variables}

    rendered_parts: list[str] = []
    index = 0
    while index < len(template):
        start = template.find("{{", index)
        if start < 0:
            rendered_parts.append(template[index:])
            break
        end = template.find("}}", start + 2)
        rendered_parts.append(template[index:start])
        variable = template[start + 2 : end].strip()
        rendered_parts.append(_render_value(values[variable]))
        index = end + 2

    rendered = "".join(rendered_parts)
    if len(rendered.encode("utf-8")) > resolved_limits.max_rendered_bytes:
        raise TemplateSecurityError("Rendered template exceeds the configured size limit.")
    return rendered


def _check_template_size(template: str, limits: TemplateLimits) -> None:
    if not isinstance(template, str):
        raise TemplateSecurityError("Template must be a string.")
    if len(template.encode("utf-8")) > limits.max_template_bytes:
        raise TemplateSecurityError("Template exceeds the configured size limit.")


def _validate_path(path: str) -> None:
    if not path:
        raise TemplateSecurityError("Template placeholder is empty.")
    if not _PATH_RE.fullmatch(path):
        raise TemplateSecurityError(f"Unsupported template expression: {path}")
    parts = path.split(".")
    if parts[0] not in _ALLOWED_ROOTS:
        raise TemplateSecurityError(f"Unsupported template variable root: {parts[0]}")
    if any(part.startswith("__") or part.endswith("__") for part in parts):
        raise TemplateSecurityError("Template paths cannot access internal names.")


def _resolve_path(context: dict[str, Any], path: str) -> Any:
    current: Any = context
    for part in path.split("."):
        if callable(current):
            raise TemplateSecurityError("Template paths cannot resolve callables.")
        if not isinstance(current, dict):
            raise TemplateSecurityError(f"Template path is not an object: {path}")
        if part not in current:
            raise TemplateSecurityError(f"Template variable is undefined: {path}")
        current = current[part]
    if callable(current):
        raise TemplateSecurityError("Template variables cannot resolve callables.")
    return current


def _render_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, int | float | bool) or value is None:
        return json.dumps(value, ensure_ascii=True, separators=(",", ":"))
    if isinstance(value, dict | list):
        return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    raise TemplateSecurityError("Template variable resolved to an unsupported value.")
