# ADR 0006: Single-Owner Authentication Boundary

## Status

Accepted for initial implementation.

## Context

Loomi-Brain must allow one owner account across multiple devices while disabling public registration. The API, not just the frontend, must enforce authentication and ownership. Cloud mode may later use OAuth, passkeys, Auth.js, Clerk, or another provider.

## Decision

Implement an auth boundary owned by the backend service layer. The initial local implementation will support a seeded owner identity, secure server-side sessions, HttpOnly SameSite cookies, CSRF protection, session revocation, and owner checks on every private resource.

Keep the auth boundary small enough that a passkey or OAuth provider can replace the credential verification mechanism without changing domain services.

## Consequences

- Phase 1 can verify owner-only API access without relying on frontend state.
- Cloud auth can be swapped later behind the same boundary.
- The product still needs careful setup-token and secret-handling documentation before remote deployment.
