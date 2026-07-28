# ADR 0005: MCP Client Transports And Safety

## Status

Accepted.

## Context

Loomi-Brain must act as an MCP client, connect only to configured servers, and support current stable transports without giving the model arbitrary tool access. The current published MCP specification defines stdio and Streamable HTTP as standard transports, with HTTP+SSE only for backward compatibility.

## Decision

Implement stdio and Streamable HTTP client support behind an MCP client boundary. Use a registry of approved servers, server/tool allowlists, typed argument validation, timeout limits, output-size limits, risk classification, approval policies, audit events, and result sanitization.

For stdio servers, use administrator-defined executable and argument templates. Reject browser-provided shell strings and shell metacharacter expansion.

## Consequences

- MCP support is useful but not an unrestricted bridge to local or external capabilities.
- The agent runtime cannot loosen MCP policy based on server metadata or tool output.
- Backward compatibility with older HTTP+SSE servers can be added only after the standard transports are working safely.
