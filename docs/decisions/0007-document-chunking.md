# ADR 0007: Deterministic Document Chunking

## Status

Accepted for Phase 2.

## Context

Ingestion needs chunk IDs that survive retries and re-indexing, preserve provenance, and remain deterministic for tests and demos. The system does not yet have retrieval evaluation data to justify a semantic splitter, model-token tokenizer, or pgvector index dimensions.

## Decision

Use a conservative character-window chunker for Phase 2:

- Normalize parser output before chunking.
- Target bounded character windows with overlap.
- Prefer paragraph and sentence breakpoints when available.
- Estimate token count as a coarse local heuristic.
- Generate stable chunk IDs from owner, document, version, checksum, ordinal, text hash, and chunker version.
- Persist parser, parser version, page/slide/sheet hints, offsets, checksum, sequence, and chunker version in provenance.

## Consequences

- Retries and re-indexing are idempotent for unchanged parser/chunker inputs.
- Tests can assert deterministic chunk IDs and embeddings.
- Chunk quality is predictable but not semantic. Search and cited chat phases may replace or augment the strategy after retrieval evaluation data exists.
