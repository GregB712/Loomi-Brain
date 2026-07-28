# ADR 0011: Explicit Agent Runtime State Machine

## Status

Accepted for Phase 4.

## Context

Phase 4 requires durable agent runs, controlled tools, owner approval, recovery hooks,
inspection UI, bounded execution, audit events, and a policy boundary that treats model
output, retrieved content, tool metadata, and tool results as untrusted data.

The current stable candidates were reviewed on 2026-07-28:

- LangGraph 1.2.9: strong graph-native fit for durable execution, typed state graphs,
  persistence, streaming, and human-in-the-loop orchestration.
- PydanticAI 2.19.0: strong typed Python ergonomics, structured output, toolsets,
  usage limits, concurrency controls, testing helpers, observability hooks, and
  deferred/human-approved tools.

Both frameworks can be useful later, but neither should own Loomi-Brain's approval
or authorization semantics. Phase 4 needs exact owner/run/tool/argument-hash binding,
single-use approval records, deterministic policy decisions, server-side allowlists,
and persisted audit history in the application database.

## Decision

Implement a custom minimal runtime behind an internal `AgentRuntime` protocol.

The runtime owns:

- the explicit state machine;
- legal transition validation;
- deterministic idempotent run IDs when an idempotency key is supplied;
- append-only run events;
- tool allowlists and server-side argument validation;
- first-party safe tools;
- approval records bound to canonical argument hashes;
- redaction, truncation, usage, latency, retry, cancellation, and audit metadata.

PydanticAI remains a future adapter candidate behind the same protocol for typed model
loops. LangGraph remains a future adapter candidate if the workflow becomes a larger
branching graph with stronger resumability needs than this slice requires.

## Consequences

- Loomi-Brain policy is code and database state, not framework or model text.
- The Phase 4 runtime stays deterministic in CI and does not require new dependencies.
- The implementation has less out-of-the-box graph tooling than LangGraph.
- If future phases add complex long-running multi-agent workflows, an adapter can map
  the internal protocol to LangGraph or PydanticAI without changing API/UI contracts.
