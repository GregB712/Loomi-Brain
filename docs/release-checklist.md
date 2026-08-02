# Release Checklist

Reader: maintainer preparing a public portfolio release.

Post-read action: decide whether the repository is ready to tag, or which release blocker must be closed first.

## Blocker

- Fresh-clone quick start must be rerun on a clean machine before tagging.
- Cloud deployment is reference architecture only until the owner verifies it on real infrastructure.
- Browser E2E, component, and accessibility tests are not yet implemented as automated suites.
- Backup restore has local artifact verification scripts, but full restore must be rehearsed against disposable development data before release.
- Container, CodeQL, SBOM, and Trivy workflows are configured but need a GitHub run before relying on their status. SARIF is retained as workflow artifacts unless repository code scanning is explicitly enabled. Trivy scans are informational artifacts for this release candidate; switch `exit-code` back to `1` when the project is ready to fail CI on findings.

## High

- In-memory login throttling protects a single API process only. Use a shared limiter before horizontal API scaling.
- The worker remains a minimal long-running skeleton. Durable job claim/retry/dead-letter behavior needs expansion before heavy production ingestion.
- Optional MinIO, ClamAV, observability, and vLLM images are configurable but not all pinned by digest because operators may need platform-specific variants.
- Private/hybrid connector option is documented as constrained architecture, not shipped as a generic public proxy.

## Medium

- Local fake scanner and mock model modes are demo-only.
- Semantic embeddings are deterministic local vectors for tests and demos; production retrieval quality requires a real embedding model and a larger evaluation set.
- Local JSONL observability retention is manual.
- CSP for the Next.js app still allows inline script/style behavior required by the framework. A nonce-based CSP is future hardening.

## Low

- Screenshots and demo GIF should be regenerated from synthetic data after the final UI pass.
- Dependency license notices should be generated from lockfiles before a public tag.
- Release notes should include exact verification output from the final CI run.

## Tag Gate

Do not tag unless these commands have passed after the last code change:

```bash
corepack pnpm format:check
make lint
make typecheck
make test
make security
make eval
corepack pnpm build
docker compose -f infra/docker/compose.yml config
docker compose -f infra/docker/compose.yml build api worker web
```

Also verify:

- No committed secrets.
- Owner login works and public registration is absent.
- Provider keys are server-side only.
- Unsafe MCP/private-network egress remains blocked by default.
- Skills cannot execute arbitrary code or bypass tool policy.
- Backup and restore artifacts are readable.
- Residual risks are documented in the release notes.
