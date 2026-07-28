# ADR 0009: Server-Sent Events For Chat Streaming

## Status

Accepted for Phase 3.

## Context

Cited chat needs streamed assistant output, typed run events, cancellation, and browser support without introducing bidirectional tool traffic yet.

## Decision

Use Server-Sent Events over authenticated POST responses for Phase 3 chat generation. The stream emits typed events: `run_started`, `retrieval_started`, `retrieval_completed`, `token_delta`, `citation`, `warning`, `usage`, `completed`, `cancelled`, and `failed`.

Run state is persisted in `agent_runs`, and emitted events are persisted in `agent_events`. Explicit cancellation updates the run state server-side. Client disconnects are handled by marking the run cancelled when the streaming coroutine is cancelled.

## Consequences

- SSE is enough for one-way assistant output and simpler than WebSockets.
- POST streaming works with `fetch`; native `EventSource` would require a separate run-creation GET stream.
- Future tool approval workflows can add WebSockets only if bidirectional realtime behavior becomes necessary.
