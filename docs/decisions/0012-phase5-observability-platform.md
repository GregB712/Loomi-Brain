# ADR 0012: Phase 5 Observability Platform

Accepted for Phase 5.

## Context

Phase 5 requires request correlation, OpenTelemetry-style traces, LLM observability,
privacy-safe telemetry, owner summaries, evaluation history, and graceful exporter
failure handling. The repository must remain runnable in local CI without paid services
or new network-installed dependencies.

## Decision

Use an internal privacy-safe telemetry recorder with OpenTelemetry-shaped span payloads,
local JSONL export, optional OTLP HTTP export, and optional Langfuse OTLP export. Store
sanitized spans in `telemetry_spans` for owner-facing product summaries. Keep prompt
content out of spans by recording stable prompt IDs and versions from a controlled prompt
registry.

Use Grafana OTEL LGTM as the default local Compose observability profile. Langfuse is
supported through the same OTLP exporter path when configured with public/secret keys and
a Langfuse endpoint.

## Consequences

- Local tests and demos do not require Langfuse, paid APIs, or OpenTelemetry SDK wheels.
- The product keeps working if exporters are unavailable.
- Trace summaries are queryable from the application database and visible in `/observability`.
- Detailed vendor trace views are linked when `LOOMI_OBSERVABILITY_TRACE_BASE_URL` is set.
- Future work can swap the recorder internals to the OpenTelemetry SDK without changing
  API routes or privacy policy.

## Privacy Controls

- Attribute allowlist before persistence/export.
- Header and query-string redaction helpers.
- Secret-pattern redaction as defense in depth.
- Maximum field-size, list, and depth limits.
- Production rejects content capture other than `none`.
- Production requires sampling at or below 25%.
