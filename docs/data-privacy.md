# Data Privacy

## Scope

Loomi-Brain stores synthetic owner-uploaded documents, extracted text chunks,
deterministic fake embeddings, parser metadata, job logs, audit events,
sanitized telemetry spans, owner feedback metadata, deterministic evaluation
reports, MCP server registry records, sanitized MCP capability metadata, skill
manifests, skill tests, skill execution metadata, voice sessions, reviewed voice
transcripts, voice provider events, and retained voice audio only when explicitly
enabled. Do not use real personal documents, credentials, or sensitive audio for demos.

## Storage

- Source objects are stored under `LOOMI_STORAGE_ROOT` with server-generated random object keys.
- Display filenames are normalized and stored only as metadata.
- Files are not stored in web/static paths.
- Chunks and embeddings remain private database records scoped to `owner_user_id`.
- Deleting a document deletes source objects, document versions, ingestion jobs, chunks, embeddings, and document tag links.
- MCP server credentials are stored as secret references, not browser-visible
  plaintext values. Capability metadata and tool output are untrusted and
  bounded before persistence/UI display.
- Skill imports and exports must not contain secrets. Published skill versions
  are immutable and remain owner-scoped.
- Voice transcripts remain private owner-scoped records. Raw voice audio is not stored by
  default. If retention is enabled, audio is stored under private object storage with a
  retention window and can be deleted independently from transcript metadata.

## Logs And Telemetry

Ordinary logs include request IDs, trace IDs, owner/document/job identifiers, media type, sizes, counts, timings, and safe error codes. They must not include document text, uploaded binaries, cookies, CSRF tokens, passwords, provider secrets, or unrestricted parser output.

Telemetry spans follow the same rule. The redaction layer allowlists attributes before
persistence/export, redacts sensitive headers and query parameters, applies secret-pattern
redaction, and enforces maximum field sizes. Production rejects prompt/response content
capture and caps sampling. Prompt IDs and versions are recorded instead of unrestricted
prompt templates or document context.

Local telemetry defaults to `local_file` under `LOOMI_STORAGE_ROOT/observability`.
External OTLP or Langfuse export is opt-in and best effort; exporter outages record a
safe status but do not break product requests.

MCP telemetry captures server IDs, capability IDs, tool names, risk classes,
schema hashes, policy outcomes, durations, status, and truncation flags. It must
not capture secret values, bearer headers, unrestricted tool arguments, or full
tool results.

Voice telemetry captures provider, model, language, voice session ID, audio duration,
audio size, TTS voice, latency, request ID, trace ID, status, and safe error codes. It
must not capture raw audio, provider secrets, cookies, authorization headers, or
unrestricted transcript content.

## Previews

Preview text is escaped before returning to the UI. HTML and Markdown from documents are never trusted as application HTML. Prompt-injection text is retained as document data so later retrieval tests can prove it cannot alter system policy.

## Scanner Behavior

Local/test mode defaults to `LOOMI_SCANNER_MODE=fake-clean`. Production must set `LOOMI_SCANNER_REQUIRED=true` and use a real scanner adapter before accepting remote uploads. If scanner policy requires a scanner and it is unavailable, ingestion fails closed.

## Export, Backup, And Deletion

Owner data export combines the database dump and private object archive. Treat
exports, backups, and restore artifacts as sensitive owner data.

Development deletion requires explicit confirmation and refuses to run outside
local/test environments. Production deletion must be adapted to the managed
database and object-store provider, with backups and audit requirements reviewed
before use.

## Limitations

URL ingestion is disabled until SSRF protections are implemented. JSON vectors are deterministic fake embeddings for tests and demos; production embeddings and pgvector indexes are deferred until retrieval evaluation defines dimensions and distance strategy.
