# ADR 0013: Phase 6 MCP Client Boundary

Date: 2026-07-29

## Status

Accepted

## Context

Phase 6 requires Loomi-Brain to connect to owner-approved MCP servers without
letting MCP metadata or results change system policy. The implementation must
support stdio local servers and the current Streamable HTTP transport, enforce
deny-by-default tool policy, and integrate with the Phase 4 agent runtime.

The reviewed MCP protocol target is `2026-07-28`. The current stable Python SDK
line is v2 and supports client construction over stdio and Streamable HTTP.

## Decision

Implement a narrow in-repo MCP client boundary first instead of adding the SDK
as a production dependency in Phase 6.

The boundary supports:

- stdio JSON-RPC over administrator-defined templates;
- Streamable HTTP JSON-RPC with redirect blocking and destination validation;
- `server/discover`, `tools/list`, `resources/list`, `prompts/list`, and
  `tools/call`;
- sanitized capability caching;
- local schema normalization and hashing;
- dynamic Phase 4 tool IDs: `mcp::<server_id>::<tool_name>`;
- audit and Phase 5 telemetry spans for registry, discovery, policy, approval,
  and execution events.

The Python SDK remains a future implementation option once dependency policy,
runtime packaging, and a larger protocol conformance test suite are ready.

## Rationale

The immediate risk is not protocol coverage; it is accidentally trusting MCP
metadata or creating a broad execution bridge. A small boundary lets Loomi own
policy enforcement before protocol objects enter the agent runtime, avoids a
new locked dependency during this phase, and keeps tests deterministic with the
built-in harmless stdio server.

## Consequences

- Phase 6 covers the product acceptance path without requiring the SDK.
- Advanced MCP features outside the selected subset are not exposed yet.
- Future SDK adoption must preserve the same registry, schema-hash approval
  binding, SSRF checks, redaction, audit, and telemetry behavior.
