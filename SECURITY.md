# Security Policy

## Supported Versions

This repository is pre-1.0. Security fixes target the current main branch until versioned releases begin.

## Reporting A Vulnerability

Open a private advisory or contact the repository owner through the configured GitHub security channel. Do not file public issues for suspected credential leaks, auth bypasses, private data exposure, unsafe MCP/tool execution, or supply-chain compromise.

Include:

- Affected commit or release.
- Reproduction steps using synthetic data.
- Impact and affected assets.
- Any request IDs, trace IDs, audit events, or logs.
- Whether secrets or personal data may have been exposed.

## Security Boundaries

- Owner-only authentication.
- No public registration.
- Server-side provider secrets.
- Private object storage.
- Backend authorization on private resources.
- Approval-gated tool execution.
- Deny-by-default MCP tools.
- Declarative skills without arbitrary code execution.

## Production Requirements

Production must use secure cookies, strict CORS/trusted hosts, real scanner policy, server-side secrets, TLS, private object storage, backups, and reviewed deployment configuration. Do not expose vLLM or MCP services directly to the public internet.
