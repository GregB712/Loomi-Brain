# Observability

Phase 5 adds privacy-safe product observability for API requests, retrieval,
model generations, agent state transitions, tool calls, approvals, ingestion
stages, owner feedback, and deterministic evaluations. Phase 6 extends the same
span model to MCP registry, connection, discovery, policy, and execution events.

## Telemetry Data Policy

Safe metadata may be captured by default:

- request IDs, trace IDs, span IDs, route paths, methods, status codes, and timings;
- owner, document, job, run, tool, approval, and message identifiers;
- retrieval mode, limits, counts, selected-context counts, warning counts, and latency;
- provider and model names, prompt IDs and versions, token totals, and estimated cost;
- ingestion stages, parser names, chunk counts, embedding counts, and safe error codes.
- MCP server IDs, capability IDs, tool names, risk classes, schema hashes, policy
  decisions, output truncation flags, and safe error codes.

Potentially sensitive values are either dropped or only represented as bounded metadata:

- prompts, model responses, retrieved excerpts, document filenames, owner comments, user
  agents, tool arguments, tool outputs, MCP results, and parser metadata.

Secrets must never be captured:

- authorization headers, cookies, CSRF/session tokens, provider keys, raw credentials,
  signed URLs, document binaries, unrestricted document text, and unredacted tool secrets.

The central redaction layer is in `loomi_api.observability.redaction`. It uses an
attribute allowlist, secret-key detection, secret-pattern redaction, query/header
redaction, depth/list limits, and maximum field sizes.

## Configuration

Key environment variables:

- `LOOMI_OBSERVABILITY_ENABLED`: enable local span recording.
- `LOOMI_OBSERVABILITY_EXPORTER`: `none`, `local_file`, `otlp_http`, or `langfuse_otlp`.
- `LOOMI_OBSERVABILITY_EXPORTER_ENDPOINT`: OTLP/Langfuse trace endpoint.
- `LOOMI_OBSERVABILITY_TRACE_BASE_URL`: base URL used to build trace links in the UI.
- `LOOMI_OBSERVABILITY_LOCAL_ONLY`: blocks external export when true.
- `LOOMI_OBSERVABILITY_SAMPLE_RATE`: deterministic trace sampling rate.
- `LOOMI_OBSERVABILITY_CONTENT_CAPTURE`: defaults to `none`; production requires `none`.
- `LOOMI_OBSERVABILITY_RETENTION_DAYS`: retention guidance for local span storage.

Telemetry export is best effort. If the exporter is missing or unavailable, the product
continues and the span records `exporter_status=failed`, `missing_endpoint`, or
`local_only`.

## Local Setup

Start the application:

```bash
make dev
```

Start the optional local observability stack:

```bash
docker compose -f infra/docker/compose.yml --profile observability up -d observability
```

The default API configuration stores local OpenTelemetry-shaped JSONL at
`LOOMI_STORAGE_ROOT/observability/telemetry.jsonl`. To test OTLP export to the local
LGTM collector, set:

```bash
LOOMI_OBSERVABILITY_EXPORTER=otlp_http
LOOMI_OBSERVABILITY_EXPORTER_ENDPOINT=http://observability:4318/v1/traces
LOOMI_OBSERVABILITY_LOCAL_ONLY=false
LOOMI_OBSERVABILITY_TRACE_BASE_URL=http://127.0.0.1:3001
```

Use the owner-facing dashboard at `/observability` for product summaries. Use the
external collector UI only for detailed trace investigation.

## Langfuse

Langfuse SDK v4 is OpenTelemetry-based. Loomi-Brain keeps the runtime dependency
optional and integrates through the `langfuse_otlp` exporter mode. Configure
`LOOMI_OBSERVABILITY_EXPORTER_ENDPOINT` to the Langfuse OTLP trace endpoint and provide
`LOOMI_OBSERVABILITY_LANGFUSE_PUBLIC_KEY` and
`LOOMI_OBSERVABILITY_LANGFUSE_SECRET_KEY`. Production should keep content capture at
`none` unless a later privacy review explicitly allows bounded redacted content.

## Evaluation

`make eval` runs deterministic synthetic evaluation with:

- lexical, semantic, and hybrid retrieval metrics;
- precision@k, recall@k, MRR, and nDCG;
- citation validity and coverage;
- groundedness and answer relevance heuristics;
- no-answer correctness;
- prompt-injection resistance and tool-policy compliance checks;
- latency, token use, and estimated cost;
- threshold-based regression failure.

Optional model-judged evaluation is explicitly disabled in default CI.
