# Loomi-Brain Implementation Plan

## Reader And Action

Reader: the engineer implementing Loomi-Brain phase by phase.

Post-read action: execute coherent, reviewable increments without skipping docs, tests, security controls, or verification.

## Operating Rules

- Work in small vertical slices.
- Do not overwrite useful existing code without explanation.
- Do not use real personal documents or credentials.
- Do not use pre-release dependencies unless an ADR justifies it.
- Generate lockfiles before claiming dependency setup is complete.
- Run formatting, linting, type checking, tests, and relevant integration checks at each phase boundary.
- Never claim a test passed unless it was executed after the last relevant change.
- If an external service is unavailable, provide a mock or fake and list the exact real integration commands.

## Phase 0: Discovery And Design

Status: complete.

Deliverables:

- Repository inspection summary.
- Product requirements.
- Architecture.
- Threat model.
- Implementation plan.
- Assumptions.
- ADRs for monorepo, agent runtime, model gateway, document extraction, MCP, and auth boundary.
- Proposed directory tree.
- Phased checklist.

Verification:

- Documentation files exist.
- Documentation files contain substantive requirements, architecture, security, and implementation content.
- Markdown is readable as plain text.
- No secrets are present.

## Phase 1: Foundation

Status: implemented.

Goal: a runnable monorepo skeleton with owner auth boundary, API health, UI shell, database migrations, local Docker services, and CI.

Work items:

1. Create monorepo directories.
2. Add root package manager metadata and pnpm workspace.
3. Add Python API and worker projects managed by uv.
4. Generate lockfiles for frontend and backend dependencies.
5. Add FastAPI application with health, readiness, liveness, request IDs, structured logs, CORS allowlist, and security headers.
6. Add SQLAlchemy async database layer and Alembic migrations for owner, sessions, documents, jobs, conversations, runs, skills, MCP, audit, and evaluation base tables.
7. Add backend-owned auth boundary with seeded owner, secure cookie settings, CSRF token flow, session revocation, and owner checks.
8. Add Next.js app shell with dashboard, navigation, themes, responsive layout, and accessible focus states.
9. Add reusable UI package foundation.
10. Add Docker Compose for PostgreSQL with pgvector, Redis, API, worker, web, optional local object store, optional ClamAV, and optional observability profile.
11. Add Makefile commands: setup, dev, test, lint, typecheck, security, migrate, seed, eval, demo, down.
12. Add CI workflow for install, format, lint, type checks, tests, builds, database integration tests, dependency scan, container build, and artifact upload where useful.

Acceptance criteria:

- `make setup` installs from lockfiles.
- `make dev` starts local services.
- API health endpoints return expected responses.
- Owner can log in and log out in local mode.
- Unauthorized document list request is blocked.
- Frontend renders the app shell on desktop and mobile.
- Initial migrations apply to PostgreSQL.

Verification commands:

- `make format`
- `make lint`
- `make typecheck`
- `make test`
- `make security`
- `corepack pnpm build`
- `docker compose -f infra/docker/compose.yml config`
- `make dev` with manual health check when Docker image pulls and port binding are available

Phase 1 implementation notes:

- The API enforces single-owner local authentication with server-side sessions, hashed session tokens, HttpOnly SameSite cookies, CSRF verification for authenticated mutations, session revocation, and audit events.
- The protected document list endpoint exists to verify the ownership boundary before ingestion lands.
- The initial migration creates base tables for owner auth, sessions, documents, jobs, conversations, runs, tools, approvals, skills, MCP, audit, feedback, and evaluation.
- PostgreSQL pgvector is enabled in the migration, but embedding vector columns and indexes are deferred to Phase 2 because dimensions and index strategy depend on ingestion and evaluation data.
- Docker Compose starts PostgreSQL, Redis, API, worker, and web by default. Optional object storage, malware scanning, and observability are Compose profiles for later integration.
- CI uses frozen installs and verifies formatting, linting, type checks, tests, frontend build, PostgreSQL migrations, security checks, dependency audit, and container builds.

## Phase 2: Knowledge Ingestion

Status: implemented.

Goal: synthetic files can be uploaded, scanned, extracted, chunked, embedded through mock/local providers, indexed, previewed, retried, re-indexed, and deleted.

Work items:

1. Upload intent and completion API.
2. Private object storage adapter.
3. ClamAV-compatible scanner interface and fake scanner.
4. Content MIME detection.
5. Docling extraction adapter with resource limits.
6. Narrow adapters for CSV, Markdown, text, and HTML where needed.
7. Chunking service with versioned strategy.
8. Embedding provider interface and deterministic mock embeddings.
9. Lexical and vector index persistence.
10. Ingestion job progress events.
11. Knowledge library UI with upload drop zone, table/card views, filters, preview, status, progress, retry, re-index, and delete.

Acceptance criteria:

- Synthetic PDF, Markdown, CSV, and hostile prompt-injection document ingest successfully or fail safely with visible status.
- Duplicate content is detected.
- Deletion removes source, chunks, embeddings, and derived assets.
- MIME mismatch is rejected or quarantined.

Verification commands:

- `make setup`
- `make lint`
- `make typecheck`
- `make test`
- `make security`
- `corepack pnpm build`
- `corepack pnpm format:check`
- `corepack pnpm peers check`
- `docker compose -f infra/docker/compose.yml config`
- `make dev` plus browser upload-to-preview verification when Docker is available

Phase 2 implementation notes:

- The API now exposes owner-scoped upload, list, detail, preview, retry, re-index, delete, tag, job-detail, and job-cancel endpoints under `/api/v1`.
- Mutating document endpoints reuse the Phase 1 session cookie and CSRF boundary. Callers never provide `owner_user_id`.
- Uploads stream into private local object storage with random keys under `LOOMI_STORAGE_ROOT`; display filenames are normalized and never used as paths.
- The default local parser stack supports PDF, DOCX, PPTX, Markdown, text, HTML, CSV, PNG, JPEG, TIFF, and WEBP through narrow adapters behind `DocumentParser`/`OCRProvider` protocols.
- `docling==2.115.0` is pinned as an optional API extra and remains behind the parser interface. The default extractor is builtin until worker isolation/resource controls are hardened further.
- Local/test scanner mode is fake and deterministic. Production configuration fails closed unless `LOOMI_SCANNER_REQUIRED=true`.
- Chunking uses ADR 0007's deterministic character-window strategy with stable chunk IDs, provenance, and version metadata.
- Embeddings use deterministic fake vectors with a fixed dimension and model name. pgvector-native indexes remain deferred until retrieval evaluation defines the production vector dimension and distance strategy.
- Background processing uses FastAPI background tasks for this slice. Redis-backed durable worker claiming remains a hardening item for later phases.
- URL ingestion is explicitly deferred until SSRF protections are implemented and tested.

## Phase 3: Search And Cited Chat

Status: implemented.

Goal: owner can search and ask questions over synthetic documents with streamed, citation-validated answers.

Work items:

1. Lexical search.
2. Vector search.
3. Hybrid rank fusion.
4. Filters and cursor pagination.
5. Retrieval debug mode.
6. Model provider gateway with mock provider, OpenAI-compatible adapter, LiteLLM adapter, and local vLLM example.
7. SSE chat stream.
8. Conversation and message persistence.
9. Citation validation.
10. Chat workspace UI with citations, source panel, trace detail, model selector, skill selector, stop/retry, copy/export, and feedback.

Acceptance criteria:

- Mock LLM answers with citations from selected chunks.
- No-answer path works when evidence is missing.
- Provider timeout does not corrupt conversation state.
- Prompt-injection fixture cannot override system policy.

Phase 3 implementation notes:

- Retrieval is implemented behind internal retriever/reranker/context assembler interfaces.
- Lexical search uses PostgreSQL FTS where available and deterministic fallback scoring in tests.
- Semantic search uses pgvector on PostgreSQL and deterministic JSON-vector cosine fallback in tests.
- Hybrid search uses reciprocal rank fusion with documented weights.
- Chat uses typed SSE events and persists run events, messages, and citations.
- Citations are validated against selected chunks; invented IDs are removed and warned.
- The model gateway includes deterministic mock plus OpenAI-compatible, OpenAI, Anthropic, Gemini, and vLLM adapters.
- Search and chat UI routes support filters, model/search-mode controls, streamed output, citations, source previews, stop/retry/copy/feedback actions, and trace/usage details.
- `make eval` produces deterministic synthetic retrieval/citation/no-answer metrics.

## Phase 4: Agent Runtime

Status: implemented.

Goal: agent runs are durable, bounded, inspectable, and enforce approval policy.

Work items:

1. Implement internal protocols: ModelProvider, EmbeddingProvider, AgentRuntime, Tool, Retriever, Reranker, TraceExporter.
2. Implement explicit state machine.
3. Persist runs, events, model calls, retrieval spans, tool calls, approvals, and errors.
4. Enforce max steps, tool limits, budgets, timeouts, cancellation, and idempotency keys.
5. Add tool registry with safe built-in tools.
6. Add approval flow.
7. Add run inspector UI with timeline, state transitions, retrieval spans, model calls, tool inputs, redacted outputs, errors, cost, latency, and trace IDs.

Acceptance criteria:

- Tool approval required for high-risk tool.
- Rejected approval moves run to a safe state.
- Max-step enforcement stops runaway loops.
- Run inspector explains what happened.

Phase 4 implementation notes:

- The runtime is a custom minimal explicit state machine behind an internal
  `AgentRuntime` protocol. ADR 0011 records the framework comparison and decision.
- Agent runs persist sanitized owner requests, allowed tools, limits, usage, latency,
  trace metadata, terminal errors, and append-only state events.
- Safe tools include `knowledge.search`, `knowledge.get_document_metadata`,
  `knowledge.get_source_excerpt`, `calculator`, and approval-required
  `notes.create_draft`.
- Approval records bind owner, run, tool call, exact tool ID, canonical argument hash,
  risk class, expiry, and single-use state.
- Denied, expired, or argument-changed approvals do not execute the tool.
- `/api/v1/agent-runs` exposes run creation, list/filter, detail, event history, SSE
  replay, cancel, retry, approve, and deny.
- `/runs` implements the Agent Run Inspector with state timeline, tool cards, approval
  cards, usage, latency, errors, cancel/retry, and accessible approve/deny controls.

## Phase 5: Observability And Evaluation

Status: implemented.

Goal: local traces, metrics, LLM observability, redaction, feedback, and synthetic evaluations work without paid services.

Work items:

1. OpenTelemetry instrumentation.
2. Langfuse adapter.
3. Redaction pipeline.
4. Prompt and response capture configuration.
5. Evaluation dataset schema and fixtures.
6. Retrieval precision/recall metrics.
7. Citation validity, groundedness, no-answer, latency, and cost checks.
8. Observability UI summaries.

Acceptance criteria:

- Trace IDs correlate UI, API, worker, retrieval, model, and tool events.
- Langfuse unavailable path is graceful.
- Evaluation command produces a report from synthetic fixtures.

Phase 5 implementation notes:

- `telemetry_spans` stores sanitized, allowlisted, bounded span attributes for API,
  retrieval, model, agent, tool, approval, and ingestion signals.
- Exporter modes are `none`, `local_file`, `otlp_http`, and `langfuse_otlp`; exporter
  failures are recorded on spans and do not break product requests.
- Production rejects telemetry content capture and sampling above 25%.
- Prompt registry entries record stable prompt IDs and versions in traces without
  unrestricted prompt or document context capture.
- `/api/v1/observability` exposes owner-only status, summary, recent runs, model usage,
  retrieval diagnostics, evaluation, and feedback endpoints with bounded date ranges.
- `/observability` provides product-level summaries and trace links.
- `make eval` now reports retrieval, citation, groundedness, no-answer, prompt-injection,
  tool-policy, latency, token, cost, and threshold regression results.

## Phase 6: MCP

Goal: owner can connect a harmless demo MCP server and invoke allowed tools while forbidden tools are blocked.

Status: implemented in Phase 6.

Work items:

1. MCP registry.
2. stdio transport client with executable templates.
3. Streamable HTTP transport client.
4. Discovery of tools, resources, and prompts.
5. Per-server and per-tool policy.
6. Typed argument validation.
7. Approval integration.
8. Result sanitization and truncation.
9. Harmless test MCP server.
10. MCP integrations UI.

Acceptance criteria:

- Allowed read-only demo tool executes.
- Forbidden tool is blocked.
- Destructive tool requires explicit approval.
- Server metadata cannot alter policy.

Implementation notes:

- `/api/v1/mcp` exposes owner-only registry, capability refresh, policy, invoke,
  and audit endpoints.
- `/mcp` provides the MCP server registry, capability list, policy editor,
  approval panel, and audit table.
- Stdio uses allowlisted templates and no shell. The built-in `loomi-test`
  server offers harmless tools and policy probes.
- Streamable HTTP endpoints are validated before use and block redirects and
  SSRF destinations by default.
- Discovered capabilities are disabled by default; enabling/lowering risk
  requires confirmation.
- Dynamic MCP tools use `mcp::<server_id>::<tool_name>` and execute through the
  Phase 4 agent runtime.
- Tool approvals bind to the local schema hash, so schema drift invalidates
  stale approvals.
- MCP registry, discovery, policy, and execution events write audit events and
  Phase 5 telemetry spans.

## Phase 7: Skills

Goal: owner can create, validate, version, test, dry-run, publish, archive, disable, import, export, and execute safe declarative skills.

Status: implemented in Phase 7.

Work items:

1. Skill manifest schema.
2. Manifest parser and validator.
3. Logic-limited templating.
4. Version and state machine.
5. Immutable published versions.
6. Test-case runner.
7. Dry-run mode.
8. Skill editor UI with structured form, manifest view, validation, preview, tests, and history.

Acceptance criteria:

- Valid skill can publish and execute.
- Invalid schema fails with useful errors.
- Forbidden template or tool fails.
- Published skill cannot be mutated.

Implementation notes:

- `/api/v1/skills` exposes owner-only create, validate, publish, archive, disable,
  clone, dry-run, execute, test, import, export, history, and diff routes.
- Skill manifests use strict `loomi.dev/v1` JSON with SemVer versions, canonical
  serialization, checksums, and unknown-field rejection.
- The Phase 7 renderer supports only bounded `{{ input.field }}`-style
  dictionary-path substitution. It rejects loops, filters, calls, imports,
  internal-object traversal, unsafe template tokens, undefined variables, and
  excessive expansion.
- Published versions are immutable. Updating a published skill requires cloning
  to a new draft version.
- Execution loads the exact published version, validates input, intersects skill
  tools with runtime/MCP policy, applies effective limits, runs through the
  Phase 4 agent runtime, and records skill IDs/version/checksum in traces.
- Dry runs and deterministic tests do not call external models or tools.
- JSON imports are reviewed and imported as drafts only; exports omit secrets and
  include tests only when explicitly requested.
- `/skills` provides the Skill Editor with structured manifest controls,
  manifest JSON, validation, dry-run preview, test runner, lifecycle actions,
  version history, diff, import review, export, and execution.

## Phase 8: Deployment And Hardening

Goal: local, cloud, and private/hybrid profiles are documented, tested, and hardened.

Work items:

1. Local Docker profile.
2. Cloud deployment profile.
3. Private/hybrid profile.
4. Security headers.
5. Rate limiting.
6. Dependency, secret, CodeQL, and container scanning.
7. Backup and restore.
8. Data export and deletion.
9. End-to-end tests.
10. README polish and screenshots.

Acceptance criteria:

- Fresh clone local setup is tested.
- Cloud deployment docs are coherent and honest.
- Backup and restore procedures are tested locally.
- CI passes all required checks.

## Proposed Directory Tree

```text
loomi-brain/
  apps/
    web/
    api/
    worker/
  packages/
    ui/
    contracts/
    config/
  infra/
    docker/
    migrations/
    deployment/
  docs/
    decisions/
  scripts/
  tests/
  .github/
    workflows/
```

## Dependency Lock Strategy

1. Use Corepack to activate a pinned pnpm version.
2. Generate pnpm lockfile after selecting frontend dependencies.
3. Use uv to create backend and worker lockfiles.
4. Reject alpha, beta, release-candidate, dev, and yanked releases unless an ADR documents the exception.
5. Run install, import smoke tests, type checks, and minimal build before accepting version pins.
6. Commit lockfiles with manifests.

## First Implementation Slice

Phase 1 should begin with a thin vertical slice:

1. API health endpoint with request ID.
2. Database connection and first migration.
3. Web app shell calling API health.
4. Docker Compose for PostgreSQL, Redis, API, worker, and web.
5. CI job that installs, lints, type-checks, tests, and builds this slice.

This slice proves the monorepo, toolchains, API contract, database, frontend, and local orchestration before deeper product features are added.
