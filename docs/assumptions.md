# Loomi-Brain Assumptions

## Reader And Action

Reader: a maintainer or reviewer checking which decisions were made without asking for clarification.

Post-read action: decide whether any assumption should be corrected before Phase 1 implementation proceeds.

## Repository

- The workspace is intended to become the Loomi-Brain repository.
- Existing empty metadata directories contain no useful source code or docs.
- Initial branch renaming is deferred because git metadata writes are restricted in this environment.

## Product

- The initial release is for one authenticated owner, not public multi-user registration.
- Synthetic fixtures are sufficient for demos and tests.
- Real personal documents and real credentials must never be committed.
- Mock providers are mandatory, not optional, so reviewers can run the project without paid AI accounts.

## Runtime

- Node.js 24.12.0 is acceptable for local development.
- pnpm will be managed through Corepack because pnpm is not currently installed.
- Python 3.14.3 is the current v1 target because uv resolved the initial API and worker locks with that runtime.
- The local machine has Python 3.10.12, so setup relies on uv-managed Python for backend and worker commands.

## Architecture

- FastAPI is the backend API framework.
- Next.js App Router is the frontend framework.
- PostgreSQL with pgvector is the source of truth for relational data, lexical search, and vector search.
- Redis is acceptable for background job brokerage in local development.
- Object storage may start with a local filesystem adapter but must keep files outside executable/static directories; S3-compatible storage is the cloud target.
- Server-Sent Events are sufficient for assistant streaming unless a later workflow proves WebSockets are required.

## AI

- PydanticAI is the default runtime for Phase 1 through Phase 4 because typed structured output and direct Python integration fit the first explicit state machine.
- LangGraph remains an alternative if durable graph orchestration becomes more valuable than typed simplicity.
- LiteLLM is acceptable only behind an internal provider adapter.
- Fallback providers stay disabled unless the owner explicitly enables them.

## Security

- Uploaded content, retrieved content, MCP content, tool output, model output, and skill manifests are untrusted.
- Owner authorization belongs in the API and service layer, not only in the frontend.
- Skills are declarative workflows, not code packages.
- MCP stdio server commands are administrator-defined templates, not browser-provided shell strings.
- Observability must redact by default.

## Deployment

- Fully local deployment is the first supported deployment profile.
- Cloud deployment uses a long-running container platform for API and worker, not Vercel serverless for the Python worker.
- Private/hybrid deployment initially prefers full-stack private machine access through Tailscale over exposing local inference to the public internet.

## Open Items For Phase 1

- Select exact pnpm version during lockfile setup.
- Decide whether backend strict type checking uses mypy, pyright, or both.
- Decide whether local object storage starts as filesystem-only or MinIO from the first slice.
- Select typed OpenAPI client generator after the FastAPI schema exists.
- Confirm Python 3.13 interpreter installation path for this machine.
