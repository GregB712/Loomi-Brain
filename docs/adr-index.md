# Architecture Decision Index

Reader: engineer evaluating why the system is shaped this way.

Post-read action: find the decision record that explains a subsystem boundary.

## Decisions

- 0001: Monorepo full-stack architecture.
- 0002: Agent runtime choice.
- 0003: Model gateway and provider adapter boundary.
- 0004: Document intelligence and extraction.
- 0005: MCP client transports and safety.
- 0006: Single-owner authentication boundary.
- 0007: Document chunking.
- 0008: Hybrid retrieval.
- 0009: SSE streaming.
- 0010: Citation validation.
- 0011: Agent runtime explicit state machine.
- 0012: Observability platform.
- 0013: MCP client boundary.
- 0014: Declarative skill model.
- 0015: Skill template and import sandbox.

## Release Rule

Add a decision record when a change introduces a durable architectural constraint, a security boundary, a deployment assumption, or a tradeoff future maintainers must preserve.
