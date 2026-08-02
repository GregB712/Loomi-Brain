from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from loomi_api.skills.renderer import TemplateSecurityError, extract_template_variables

API_VERSION = "loomi.dev/v1"
KIND = "Skill"
MAX_MANIFEST_BYTES = 96_000
MAX_SCHEMA_DEPTH = 8
MAX_SCHEMA_PROPERTIES = 80
MAX_TOOL_COUNT = 20
SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
SKILL_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{2,79}$")
MCP_TOOL_RE = re.compile(r"^mcp::[A-Za-z0-9_-]{1,64}::[A-Za-z0-9_.-]{1,120}$")
BUILT_IN_TOOL_IDS = {
    "knowledge.search",
    "knowledge.get_document_metadata",
    "knowledge.get_source_excerpt",
    "calculator",
    "notes.create_draft",
}
MODEL_CAPABILITIES = {"fast", "balanced", "reasoning"}
LIFECYCLE_STATES = {"draft", "published", "archived", "disabled"}
JSON_SCHEMA_TYPES = {"object", "array", "string", "integer", "number", "boolean", "null"}
JSON_SCHEMA_KEYS = {
    "type",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "enum",
    "minLength",
    "maxLength",
    "minimum",
    "maximum",
    "minItems",
    "maxItems",
    "title",
    "description",
    "default",
}


class SkillMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=3, max_length=80)
    version: str = Field(min_length=5, max_length=40)
    description: str = Field(min_length=1, max_length=1000)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not SKILL_NAME_RE.fullmatch(value):
            raise ValueError("Skill name must be normalized lowercase kebab-case.")
        return value

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        if not SEMVER_RE.fullmatch(value):
            raise ValueError("Skill version must be semantic version syntax.")
        return value


class RetrievalPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["none", "lexical", "semantic", "hybrid"] = "hybrid"
    topK: int = Field(default=8, ge=0, le=20)


class ApprovalPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["runtime", "always"] = "runtime"


class ModelPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability: Literal["fast", "balanced", "reasoning"] = "reasoning"
    maxInputTokens: int = Field(default=12_000, ge=1, le=50_000)
    maxOutputTokens: int = Field(default=2_000, ge=1, le=10_000)


class SkillLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    maxSteps: int = Field(default=6, ge=1, le=64)
    maxToolCalls: int = Field(default=3, ge=0, le=12)
    timeoutSeconds: int = Field(default=120, ge=1, le=300)


class SkillSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inputSchema: dict[str, Any] = Field(default_factory=dict)
    outputSchema: dict[str, Any] = Field(default_factory=dict)
    promptTemplate: str = Field(min_length=1, max_length=16_000)
    retrievalPolicy: RetrievalPolicy = Field(default_factory=RetrievalPolicy)
    allowedTools: list[str] = Field(default_factory=list, max_length=MAX_TOOL_COUNT)
    approvalPolicy: ApprovalPolicy = Field(default_factory=ApprovalPolicy)
    modelPolicy: ModelPolicy = Field(default_factory=ModelPolicy)
    limits: SkillLimits = Field(default_factory=SkillLimits)


class SkillManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    apiVersion: Literal["loomi.dev/v1"]
    kind: Literal["Skill"]
    metadata: SkillMetadata
    spec: SkillSpec


@dataclass(frozen=True)
class ValidationIssue:
    path: str
    code: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"path": self.path, "code": self.code, "detail": self.detail}


@dataclass(frozen=True)
class ManifestValidationResult:
    valid: bool
    errors: tuple[ValidationIssue, ...]
    warnings: tuple[ValidationIssue, ...]
    canonical_manifest: dict[str, Any] | None = None
    checksum: str | None = None
    normalized_name: str | None = None
    version: str | None = None
    variable_refs: tuple[str, ...] = ()
    requested_tools: tuple[str, ...] = ()
    permissions_summary: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": [issue.as_dict() for issue in self.errors],
            "warnings": [issue.as_dict() for issue in self.warnings],
            "canonical_manifest": self.canonical_manifest,
            "checksum": self.checksum,
            "normalized_name": self.normalized_name,
            "version": self.version,
            "variable_refs": list(self.variable_refs),
            "requested_tools": list(self.requested_tools),
            "permissions_summary": self.permissions_summary,
        }


def validate_manifest(
    payload: dict[str, Any],
    *,
    runtime_tool_ids: set[str] | None = None,
) -> ManifestValidationResult:
    size = len(json.dumps(payload, ensure_ascii=True, default=str).encode("utf-8"))
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    if size > MAX_MANIFEST_BYTES:
        errors.append(
            ValidationIssue("$", "manifest_too_large", "Manifest exceeds the size limit.")
        )
    try:
        manifest = SkillManifest.model_validate(payload)
    except ValidationError as exc:
        errors.extend(_pydantic_errors(exc))
        return ManifestValidationResult(
            valid=False,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )

    _validate_json_schema(manifest.spec.inputSchema, "$.spec.inputSchema", errors)
    _validate_json_schema(manifest.spec.outputSchema, "$.spec.outputSchema", errors)

    try:
        variable_refs = extract_template_variables(manifest.spec.promptTemplate)
    except TemplateSecurityError as exc:
        errors.append(ValidationIssue("$.spec.promptTemplate", "unsafe_template", str(exc)))
        variable_refs = ()
    for variable in variable_refs:
        if not _variable_allowed_by_schema(variable, manifest.spec.inputSchema):
            errors.append(
                ValidationIssue(
                    "$.spec.promptTemplate",
                    "undefined_template_variable",
                    f"Template variable is not allowed by the input schema: {variable}",
                )
            )

    requested_tools = tuple(dict.fromkeys(manifest.spec.allowedTools))
    if len(requested_tools) != len(manifest.spec.allowedTools):
        warnings.append(
            ValidationIssue(
                "$.spec.allowedTools",
                "duplicate_tool_removed",
                "Duplicate tool IDs collapse during canonicalization.",
            )
        )
    for tool_id in requested_tools:
        if not _valid_tool_id(tool_id):
            errors.append(
                ValidationIssue(
                    "$.spec.allowedTools",
                    "unsupported_tool",
                    f"Tool is not a built-in tool or canonical MCP tool ID: {tool_id}",
                )
            )
    if runtime_tool_ids is not None:
        missing = sorted(set(requested_tools) - runtime_tool_ids)
        if missing:
            warnings.append(
                ValidationIssue(
                    "$.spec.allowedTools",
                    "tool_not_enabled_by_runtime",
                    f"Requested tools are not currently enabled by server policy: {missing}",
                )
            )

    canonical = canonical_manifest(manifest)
    checksum = checksum_manifest(canonical)
    return ManifestValidationResult(
        valid=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
        canonical_manifest=canonical,
        checksum=checksum,
        normalized_name=manifest.metadata.name,
        version=manifest.metadata.version,
        variable_refs=variable_refs,
        requested_tools=requested_tools,
        permissions_summary={
            "allowed_tools": list(requested_tools),
            "approval_mode": manifest.spec.approvalPolicy.mode,
            "retrieval": manifest.spec.retrievalPolicy.model_dump(mode="json"),
            "model_policy": manifest.spec.modelPolicy.model_dump(mode="json"),
            "limits": manifest.spec.limits.model_dump(mode="json"),
        },
    )


def canonical_manifest(manifest: SkillManifest) -> dict[str, Any]:
    payload = manifest.model_dump(mode="json")
    payload["spec"]["allowedTools"] = sorted(dict.fromkeys(payload["spec"]["allowedTools"]))
    return payload


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def checksum_manifest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def validate_json_data(
    value: Any,
    schema: dict[str, Any],
    *,
    path: str = "$",
) -> tuple[ValidationIssue, ...]:
    errors: list[ValidationIssue] = []
    _validate_json_value(value, schema, path, errors)
    return tuple(errors)


def synthetic_input_for_schema(schema: dict[str, Any]) -> dict[str, Any]:
    if not schema or schema.get("type") != "object":
        return {}
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        return {}
    output: dict[str, Any] = {}
    for name, field_schema in properties.items():
        if isinstance(field_schema, dict):
            output[str(name)] = _synthetic_value(field_schema)
    return output


def normalize_lifecycle_state(value: str) -> str:
    if value not in LIFECYCLE_STATES:
        raise ValueError(f"Unsupported skill lifecycle state: {value}")
    return value


def _pydantic_errors(exc: ValidationError) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for error in exc.errors():
        loc = ".".join(str(part) for part in error["loc"])
        issues.append(
            ValidationIssue(
                f"$.{loc}" if loc else "$",
                str(error["type"]),
                str(error["msg"]),
            )
        )
    return issues


def _validate_json_schema(
    schema: Any,
    path: str,
    errors: list[ValidationIssue],
    *,
    depth: int = 0,
) -> None:
    if not isinstance(schema, dict):
        errors.append(ValidationIssue(path, "invalid_json_schema", "Schema must be an object."))
        return
    if depth > MAX_SCHEMA_DEPTH:
        errors.append(ValidationIssue(path, "schema_too_deep", "Schema nesting is too deep."))
        return
    unknown = sorted(set(schema) - JSON_SCHEMA_KEYS)
    for key in unknown:
        errors.append(
            ValidationIssue(
                f"{path}.{key}",
                "unsupported_schema_keyword",
                f"Unsupported JSON Schema keyword: {key}",
            )
        )
    schema_type = schema.get("type")
    if schema_type is not None and schema_type not in JSON_SCHEMA_TYPES:
        errors.append(
            ValidationIssue(
                f"{path}.type",
                "unsupported_schema_type",
                f"Unsupported JSON Schema type: {schema_type}",
            )
        )
    required = schema.get("required")
    if required is not None and (
        not isinstance(required, list) or not all(isinstance(item, str) for item in required)
    ):
        errors.append(
            ValidationIssue(f"{path}.required", "invalid_required", "Required must be strings.")
        )
    properties = schema.get("properties")
    if properties is not None:
        if not isinstance(properties, dict):
            errors.append(
                ValidationIssue(
                    f"{path}.properties",
                    "invalid_properties",
                    "Properties must be an object.",
                )
            )
        elif len(properties) > MAX_SCHEMA_PROPERTIES:
            errors.append(
                ValidationIssue(
                    f"{path}.properties",
                    "too_many_properties",
                    "Schema has too many properties.",
                )
            )
        else:
            for name, child in properties.items():
                _validate_json_schema(child, f"{path}.properties.{name}", errors, depth=depth + 1)
    items = schema.get("items")
    if items is not None:
        _validate_json_schema(items, f"{path}.items", errors, depth=depth + 1)
    for key in ("minLength", "maxLength", "minItems", "maxItems"):
        value = schema.get(key)
        if value is not None and (not isinstance(value, int) or value < 0):
            errors.append(ValidationIssue(f"{path}.{key}", "invalid_limit", "Limit must be >= 0."))
    for key in ("minimum", "maximum"):
        value = schema.get(key)
        if value is not None and not isinstance(value, int | float):
            errors.append(
                ValidationIssue(f"{path}.{key}", "invalid_limit", "Limit must be numeric.")
            )
    additional = schema.get("additionalProperties")
    if additional is not None and not isinstance(additional, bool):
        errors.append(
            ValidationIssue(
                f"{path}.additionalProperties",
                "unsupported_additional_properties",
                "Only boolean additionalProperties is supported.",
            )
        )


def _validate_json_value(
    value: Any,
    schema: dict[str, Any],
    path: str,
    errors: list[ValidationIssue],
) -> None:
    if not schema:
        return
    expected_type = schema.get("type")
    if expected_type and not _matches_type(value, str(expected_type)):
        errors.append(ValidationIssue(path, "schema_type_mismatch", f"Expected {expected_type}."))
        return
    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and value not in enum_values:
        errors.append(ValidationIssue(path, "schema_enum_mismatch", "Value is not in enum."))
        return
    if isinstance(value, str):
        min_length = schema.get("minLength")
        max_length = schema.get("maxLength")
        if isinstance(min_length, int) and len(value) < min_length:
            errors.append(ValidationIssue(path, "string_too_short", "String is too short."))
        if isinstance(max_length, int) and len(value) > max_length:
            errors.append(ValidationIssue(path, "string_too_long", "String is too long."))
    if isinstance(value, int | float) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if isinstance(minimum, int | float) and value < minimum:
            errors.append(ValidationIssue(path, "number_too_small", "Number is below minimum."))
        if isinstance(maximum, int | float) and value > maximum:
            errors.append(ValidationIssue(path, "number_too_large", "Number is above maximum."))
    if isinstance(value, list):
        max_items = schema.get("maxItems")
        min_items = schema.get("minItems")
        if isinstance(min_items, int) and len(value) < min_items:
            errors.append(ValidationIssue(path, "array_too_short", "Array has too few items."))
        if isinstance(max_items, int) and len(value) > max_items:
            errors.append(ValidationIssue(path, "array_too_long", "Array has too many items."))
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate_json_value(item, item_schema, f"{path}[{index}]", errors)
    if isinstance(value, dict):
        required = schema.get("required")
        if isinstance(required, list):
            for name in required:
                if isinstance(name, str) and name not in value:
                    errors.append(
                        ValidationIssue(
                            f"{path}.{name}",
                            "schema_required_missing",
                            f"Required property is missing: {name}",
                        )
                    )
        properties = schema.get("properties")
        known = properties if isinstance(properties, dict) else {}
        additional = schema.get("additionalProperties", True)
        if additional is False:
            for key in value:
                if key not in known:
                    errors.append(
                        ValidationIssue(
                            f"{path}.{key}",
                            "schema_unknown_property",
                            f"Unknown property: {key}",
                        )
                    )
        for key, child_schema in known.items():
            if key in value and isinstance(child_schema, dict):
                _validate_json_value(value[key], child_schema, f"{path}.{key}", errors)


def _matches_type(value: Any, expected_type: str) -> bool:
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "null":
        return value is None
    return False


def _synthetic_value(schema: dict[str, Any]) -> Any:
    if "default" in schema:
        return schema["default"]
    schema_type = schema.get("type")
    if schema_type == "string":
        enum_values = schema.get("enum")
        if isinstance(enum_values, list) and enum_values:
            return enum_values[0]
        return "synthetic"
    if schema_type == "integer":
        return int(schema.get("minimum", 1))
    if schema_type == "number":
        return float(schema.get("minimum", 1.0))
    if schema_type == "boolean":
        return True
    if schema_type == "array":
        item_schema = schema.get("items")
        return [_synthetic_value(item_schema)] if isinstance(item_schema, dict) else []
    if schema_type == "object":
        return synthetic_input_for_schema(schema)
    return "synthetic"


def _variable_allowed_by_schema(variable: str, schema: dict[str, Any]) -> bool:
    parts = variable.split(".")
    root = parts[0]
    if root in {"retrieval", "tools", "skill"}:
        return True
    if root != "input":
        return False
    if len(parts) == 1:
        return True
    current: dict[str, Any] = schema
    for part in parts[1:]:
        if not current:
            return True
        properties = current.get("properties")
        if not isinstance(properties, dict):
            return current.get("additionalProperties", True) is True
        child = properties.get(part)
        if not isinstance(child, dict):
            return current.get("additionalProperties", True) is True
        current = child
    return True


def _valid_tool_id(tool_id: str) -> bool:
    if tool_id in BUILT_IN_TOOL_IDS:
        return True
    return MCP_TOOL_RE.fullmatch(tool_id) is not None
