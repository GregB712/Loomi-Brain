# Changelog

## v0.1.0 Candidate

- Added Phase 8 API/web security hardening: CSP/security headers, trusted hosts, request-size guard, and login rate limiting.
- Converted API, worker, and web Dockerfiles to production-oriented non-root runtime images.
- Hardened Compose with localhost bindings, separated networks, health checks, restart policies, dropped capabilities, read-only app filesystems, named volumes, and optional storage/scan/observability/LLM profiles.
- Added backup, restore verification, object restore, owner export, guarded local deletion, and disaster-recovery smoke scripts.
- Added Dependabot, CodeQL, Trivy filesystem/container scanning, SBOM artifact generation, and manual release packaging workflows.
- Reworked README and added release, operations, backup/restore, private/hybrid, demo, incident-response, performance, and ADR-index documentation.

## v0.0.0

- Initial monorepo, owner-auth boundary, ingestion, retrieval, cited chat, agent runtime, observability, MCP, and skills phases.
