# ADR 0002: Default Agent Runtime

## Status

Accepted for initial implementation.

## Context

The system requires provider-neutral agents with typed structured output, streaming, tools, persistence, approval gates, observability, testing, and bounded execution. The main candidates are PydanticAI and LangGraph.

## Options

### PydanticAI

Strengths:

- Strong fit for Pydantic v2 and typed structured outputs.
- Direct Python ergonomics.
- Stable PyPI classification and Python 3.10 through 3.14 classifiers at Phase 0.
- Good fit for a manually explicit state machine.

Weaknesses:

- Less graph-native than LangGraph for complex long-lived workflows.
- Persistence and resumability patterns must be designed carefully in Loomi-Brain.

### LangGraph

Strengths:

- Graph-native runtime with durable workflow concepts.
- Mature ecosystem around agent state graphs.
- Good fit if the state machine becomes highly branching or resumability-heavy.

Weaknesses:

- Additional framework surface area.
- Phase 0 metadata shows Python 3.13 support but not Python 3.14 classification.
- Can add conceptual overhead before the product needs it.

## Decision

Use PydanticAI as the default runtime behind an internal AgentRuntime protocol. Implement Loomi-Brain's own explicit state machine, persistence model, approval policy, and event schema so the runtime can be swapped later.

## Consequences

- Initial implementation stays typed and explicit.
- The project avoids coupling product policy to framework internals.
- LangGraph can be adopted later for the AgentRuntime adapter if the workflow complexity justifies it.
