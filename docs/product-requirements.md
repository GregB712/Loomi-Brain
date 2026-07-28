# Loomi-Brain Product Requirements

## Reader And Action

Reader: an engineer or reviewer landing on Loomi-Brain without prior context.

Post-read action: understand what the initial release must do, what it must not do, and how success will be evaluated.

## Summary

Loomi-Brain is a secure, single-owner second-brain application for ingesting private knowledge, retrieving it with lexical and semantic search, chatting with it through cited answers, and running controlled agent workflows. It is intended to demonstrate production-grade AI platform engineering, backend design, security, observability, evaluation, and a reusable web interface.

The product is single-user but multi-device. The security model assumes every uploaded document, retrieved passage, imported web page, model output, tool result, MCP server response, and skill manifest is untrusted.

## Initial Release Goals

1. Authenticate exactly one owner account and enforce owner access in the API.
2. Upload, validate, parse, chunk, embed, index, search, preview, re-index, and delete synthetic documents.
3. Support PDF, DOCX, PPTX, Markdown, plain text, HTML, CSV, common image formats, and safe supported URLs.
4. Provide lexical, semantic, and hybrid retrieval over PostgreSQL full-text search and pgvector.
5. Stream chat responses with precise citations, selected context, model metadata, latency, token usage, approximate cost, warnings, and trace IDs.
6. Provide a deterministic mock LLM mode for demos and tests.
7. Wrap model vendors behind provider-neutral interfaces for chat, classification, embeddings, reranking, and vision/OCR.
8. Persist agent runs and events with bounded steps, budgets, timeouts, approvals, and cancellation.
9. Connect to explicitly configured MCP servers through stdio and Streamable HTTP, with tool allowlists, typed arguments, risk classes, and owner approval.
10. Provide a safe, declarative, versioned skills system without arbitrary code execution.
11. Show observability for ingestion, retrieval, model calls, tool calls, cost, latency, errors, and evaluation results.
12. Ship local, cloud, and private/hybrid deployment documentation with realistic limitations.

## Non-Goals

- Public registration or multi-tenant billing.
- Social features or collaboration.
- Autonomous execution without hard limits and approval controls.
- Training foundation models.
- Arbitrary skill code, shell commands, SQL, dynamic package installation, or unrestricted filesystem/network access.
- Trusting instructions embedded in documents, web pages, MCP metadata, MCP responses, tool output, or model output.
- Running persistent Python workers on Vercel serverless functions.

## Personas

### Owner

The owner maintains private knowledge, asks questions with citations, inspects evidence, configures providers, approves sensitive tool calls, and exports or deletes data.

### Reviewer

The reviewer evaluates architecture, security posture, tests, observability, and demo quality without needing paid model credentials or real personal documents.

### Contributor

The contributor needs clear boundaries for backend services, frontend components, contracts, migrations, tests, and docs.

## Core Workflows

### Owner Setup And Login

1. Owner identity is seeded by environment variable or secure setup flow.
2. Public registration remains disabled.
3. Owner logs in from multiple devices.
4. API validates session and owner ownership for private resources.
5. Owner can revoke sessions.

### Document Ingestion

1. Owner uploads or imports content.
2. API validates request, size, media limits, and ownership.
3. Worker performs malware scan, MIME detection from content, extraction, OCR when needed, normalization, chunking, embedding, indexing, and provenance persistence.
4. UI shows status, progress, warnings, retry options, preview, re-index, and delete actions.
5. Deletion removes source, chunks, embeddings, derived assets, and related traces that are legally and technically deletable.

### Search

1. Owner chooses lexical, semantic, or hybrid mode.
2. Owner applies filters for collections, tags, source type, document, status, or date.
3. API returns paginated results with excerpts, scores, source metadata, and debug details when enabled.
4. UI explains why a result was selected without exposing secrets or raw internal prompts.

### Cited Chat

1. Owner asks a question.
2. Agent classifies intent, retrieves context, assembles a bounded prompt, and streams answer events.
3. Answer cites concrete document chunks and exposes selected evidence.
4. If evidence is insufficient, the assistant says it cannot answer from the current knowledge base.
5. Conversation state is not corrupted by provider timeouts, cancellation, or failures.

### Agent Tool Approval

1. Agent proposes a tool call.
2. Runtime classifies the call by risk.
3. Read-only allowlisted calls may run automatically when policy permits.
4. Local mutation, external mutation, credential-sensitive, and destructive calls require explicit owner approval.
5. Tool result is sanitized, truncated when needed, persisted, and treated as untrusted context.

### Skills

1. Owner creates a declarative skill manifest using a structured editor.
2. Manifest is validated against JSON Schema.
3. Draft skills can be dry-run with synthetic test cases.
4. Published versions are immutable.
5. Disabled or archived skills cannot execute.

## Functional Requirements

### Knowledge

- Store documents, versions, ingestion jobs, chunks, embeddings, tags, collections, provenance, and deletion state.
- Use content-addressed deduplication.
- Re-ingest when parser, chunker, or embedding versions change.
- Preserve page references, heading paths, tables, offsets where practical, parser version, embedding model, and ingestion timestamps.
- Enforce size, page count, decompression, parser runtime, and response limits.

### Retrieval

- Provide PostgreSQL full-text search.
- Provide pgvector semantic search.
- Provide hybrid rank fusion.
- Support metadata and collection filters.
- Support optional reranking through an internal interface.
- Assemble context within a token budget.
- Include retrieval debug mode for reviewers.

### Model Gateway

- Support OpenAI-compatible APIs, OpenAI, Anthropic, Google Gemini, local vLLM, and future providers behind adapters.
- Separate models for reasoning/chat, fast classification, embeddings, optional reranking, and optional vision/OCR.
- Provide provider health checks, capability metadata, timeouts, bounded retries, rate limits, token accounting, cost estimation, and safe error messages.
- Keep provider secrets server-side only.
- Disable fallback providers by default unless the owner explicitly enables them.

### MCP Client

- Maintain an MCP server registry.
- Support stdio and Streamable HTTP transports.
- Discover tools, resources, and prompts but do not let server metadata alter policy.
- Validate typed arguments.
- Enforce server and tool allowlists, timeout limits, output-size limits, and approval policies.
- Persist audit events for discovery, approval, execution, failure, and disablement.

### Observability And Evaluation

- Emit correlated logs, metrics, and traces across web, API, worker, agent, retrieval, and provider calls.
- Surface trace IDs in the UI.
- Redact secrets, credentials, cookies, authorization headers, binaries, unrestricted document text, and sensitive tool output before export.
- Provide synthetic evaluation datasets for retrieval, citations, groundedness, no-answer behavior, prompt-injection resistance, approval enforcement, provider failures, and streaming cancellation.

## Non-Functional Requirements

### Security

- Deny by default.
- Validate strict request and response schemas.
- Check authentication and owner authorization in API and service layers.
- Avoid raw model-generated HTML. Render Markdown with raw HTML disabled and sanitized links.
- Protect upload, URL import, search, chat, and tool endpoints with rate limits.
- Use secret references whenever an external secret manager is available.
- Use dependency lockfiles, secret scanning, vulnerability scanning, CodeQL, container scanning, and non-root containers.

### Reliability

- Persist ingestion and agent state before side effects.
- Use idempotency keys for side-effecting actions.
- Retry transient failures with bounded exponential backoff and jitter.
- Make cancellation explicit and durable.
- Degrade gracefully when providers, observability, ClamAV, or optional local model services are unavailable.

### Accessibility And UX

- Meet WCAG 2.2 AA where practical.
- Provide keyboard navigation, visible focus, semantic HTML, accessible labels, responsive behavior, and reduced-motion support.
- Make the first screen a usable application dashboard, not a marketing landing page.
- Keep operational tools dense, predictable, and scannable.

### Developer Experience

- Use a monorepo.
- Use pnpm workspaces for TypeScript packages.
- Use uv for Python environments and lockfiles.
- Use Ruff, strict type checking, pytest, ESLint, Prettier, Playwright, pre-commit hooks, a Makefile, and GitHub Actions.
- Provide deterministic demo mode with synthetic data and mock model output.

## Success Metrics

- Fresh clone starts locally from documented commands.
- Owner-only access is verified by tests.
- Synthetic document upload, parse, index, search, cite, re-index, and delete workflows pass.
- Chat streams answer events and citations.
- Mock LLM mode works without paid credentials.
- Forbidden MCP tools are blocked and audited.
- Prompt injection inside a test document does not gain system authority.
- Lint, formatting, type checks, tests, builds, and container checks pass in CI.
- README and docs explain architecture, threat model, tradeoffs, demo mode, and deployment.

## Major Risks And Mitigations

1. Prompt injection from documents and tools - separate instruction tiers, label retrieved content as untrusted, test hostile fixtures, and block tool-policy changes from untrusted content.
2. Parser vulnerabilities and malicious uploads - content MIME detection, ClamAV adapter, size limits, decompression limits, worker resource limits, and isolated storage outside executable/static paths.
3. SSRF in URL import - allow only HTTP/HTTPS, validate DNS and redirects, block private/reserved ranges, cap redirects, cap bytes, and apply timeouts.
4. MCP tool escalation - administrator-defined server registry, executable templates only, no browser-provided shell strings, allowlists, risk classification, owner approval, and output sanitization.
5. Secret and telemetry leakage - server-side secrets only, redaction before logging/export, opt-in prompt capture, and no binaries or unrestricted document text in telemetry.
6. Excessive model/tool spend - request budgets, token accounting, rate limits, max steps, timeout cancellation, and disabled-by-default fallbacks.
7. Dependency churn - pinned lockfiles, version ADRs, renovate policy, compatibility tests, and explicit rejection of pre-releases without ADRs.
8. pgvector/index tradeoffs - document distance metric, expected dataset size, index type, migration path, and retrieval evaluation before optimizing prematurely.
9. Single-owner assumptions becoming hidden multi-tenant risk - keep owner_id on sensitive records and enforce owner checks even in v1.
10. Demo realism without private data - use synthetic fixtures only, include hostile prompt-injection examples, and label mock responses clearly.

## Open Decisions

No decision currently blocks Phase 1. Authentication provider and cloud hosting can be swapped behind boundaries defined in the architecture. Exact dependency pins will be finalized through lockfile generation before implementation code is claimed complete.
