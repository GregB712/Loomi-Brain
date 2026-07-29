# Data Privacy

## Scope

Phase 5 stores synthetic owner-uploaded documents, extracted text chunks, deterministic fake embeddings, parser metadata, job logs, audit events, sanitized telemetry spans, owner feedback metadata, and deterministic evaluation reports. Do not use real personal documents or credentials for demos.

## Storage

- Source objects are stored under `LOOMI_STORAGE_ROOT` with server-generated random object keys.
- Display filenames are normalized and stored only as metadata.
- Files are not stored in web/static paths.
- Chunks and embeddings remain private database records scoped to `owner_user_id`.
- Deleting a document deletes source objects, document versions, ingestion jobs, chunks, embeddings, and document tag links.

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

## Previews

Preview text is escaped before returning to the UI. HTML and Markdown from documents are never trusted as application HTML. Prompt-injection text is retained as document data so later retrieval tests can prove it cannot alter system policy.

## Scanner Behavior

Local/test mode defaults to `LOOMI_SCANNER_MODE=fake-clean`. Production must set `LOOMI_SCANNER_REQUIRED=true` and use a real scanner adapter before accepting remote uploads. If scanner policy requires a scanner and it is unavailable, ingestion fails closed.

## Limitations

URL ingestion is disabled until SSRF protections are implemented. JSON vectors are deterministic fake embeddings for tests and demos; production embeddings and pgvector indexes are deferred until retrieval evaluation defines dimensions and distance strategy.
