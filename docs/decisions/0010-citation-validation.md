# ADR 0010: Citation Validation Strategy

## Status

Accepted for Phase 3.

## Context

Model output is untrusted and may invent citation identifiers. Grounded answers must only cite selected stored chunks.

## Decision

The context assembler assigns opaque allowed IDs such as `ctx_1` to selected chunks. Provider prompts instruct models to cite only those IDs. The server validates returned citation IDs against the selected context and removes or warns on fabricated IDs before persisting or streaming citations.

Citation payloads include document ID, document title, document version, chunk ID, available page/slide/sheet/section provenance, excerpt, and a source preview locator.

## Consequences

- The model cannot create authority for chunks that were not selected.
- Citations remain verifiable through `/api/v1/sources/chunks/{chunk_id}`.
- This does not solve prompt injection perfectly; it narrows what grounded answers are allowed to claim.
