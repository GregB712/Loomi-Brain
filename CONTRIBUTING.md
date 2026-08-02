# Contributing

Loomi-Brain is an owner-led portfolio project. Contributions are welcome when they preserve the owner-only privacy and security model.

## Ground Rules

- Do not add real personal documents, real credentials, private infrastructure identifiers, or live provider keys.
- Keep provider secrets server-side. Never introduce `NEXT_PUBLIC_` secrets.
- Preserve backend authorization for every private resource.
- Treat document text, model output, MCP metadata, tool output, and skill manifests as untrusted.
- Add or update tests for behavior changes.
- Update docs when behavior, operations, deployment, or security posture changes.

## Local Checks

```bash
corepack pnpm format:check
make lint
make typecheck
make test
make security
make eval
corepack pnpm build
docker compose -f infra/docker/compose.yml config
```

Container builds are required for release-impacting changes:

```bash
docker compose -f infra/docker/compose.yml build api worker web
```

## Pull Requests

Include:

- What changed.
- Why it changed.
- Security/privacy impact.
- Tests and commands run.
- Screenshots for UI changes, using synthetic data only.
- Residual risks or follow-up work.
