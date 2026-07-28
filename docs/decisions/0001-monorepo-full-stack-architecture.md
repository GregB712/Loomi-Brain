# ADR 0001: Monorepo Full-Stack Architecture

## Status

Accepted.

## Context

Loomi-Brain needs a frontend, API, worker, shared UI components, shared contracts, infrastructure, tests, and documentation. The project is intended as a portfolio repository, so reviewers should be able to inspect the complete system in one place.

## Decision

Use a monorepo with separate application modules for web, API, and worker, shared packages for UI, contracts, and configuration, and top-level infrastructure, scripts, tests, and documentation.

## Consequences

- One repository can show end-to-end product, platform, security, and MLOps work.
- Shared contracts and UI components are easier to evolve.
- CI can validate cross-boundary changes.
- Tooling must be carefully scoped so Node and Python lockfiles remain independent and reproducible.
