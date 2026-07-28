# Tool Development

Phase 4 tools are first-party server-side implementations. The model may suggest an
intent, but the runtime decides which registered tool can run.

## Tool Contract

Every tool must define:

- stable `id`;
- description;
- JSON input schema;
- JSON output schema where practical;
- risk class;
- timeout;
- output-size limit;
- idempotency behavior;
- approval policy;
- execution implementation.

Risk classes are:

- `read-only`;
- `local-mutation`;
- `external-mutation`;
- `credential-sensitive`;
- `destructive`.

## Allowed Tools

Phase 4 ships:

- `knowledge.search`;
- `knowledge.get_document_metadata`;
- `knowledge.get_source_excerpt`;
- `calculator`;
- `notes.create_draft`.

Do not add arbitrary shell, filesystem, Python execution, raw SQL, unrestricted HTTP, or
email-sending tools.

## Security Rules

- Validate arguments server-side before creating a tool call.
- Enforce owner authorization inside each tool implementation.
- Never trust model-provided owner IDs, resource IDs, policy text, risk labels, or approval
  state.
- Redact and truncate tool output before persistence.
- Store tool calls and approvals with trace IDs and policy decisions.
- Add tests for schema validation, allowlisting, approval behavior, redaction, and
  prompt-injection attempts.
