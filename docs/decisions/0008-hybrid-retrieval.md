# ADR 0008: Hybrid Retrieval Strategy

## Status

Accepted for Phase 3.

## Context

Phase 3 requires lexical, semantic, and hybrid search over owner documents while keeping deterministic CI behavior. PostgreSQL with pgvector remains the production target, but tests run on SQLite.

## Decision

Use PostgreSQL full-text search for lexical retrieval and pgvector cosine distance for production semantic retrieval. Local/test mode uses the same service boundary with deterministic Python scoring over stored chunks and JSON embeddings.

Hybrid search uses reciprocal rank fusion with lexical weight `1.0`, semantic weight `0.85`, and `k=60`. Results then pass through source diversity, duplicate suppression, minimum score filtering, and token-budget context assembly.

The Phase 3 migration adds a PostgreSQL `vector(16)` column for the current deterministic embedding dimension, an HNSW cosine index, and a GIN FTS index. If embedding dimensions change, the vector column/index must be migrated with the embedding model version.

## Consequences

- RRF is simple, explainable, and robust when lexical and semantic scores are not directly comparable.
- SQLite fallback keeps CI deterministic without Postgres.
- The fixed `vector(16)` index is appropriate for the current synthetic/demo scale, not for final production embeddings.
