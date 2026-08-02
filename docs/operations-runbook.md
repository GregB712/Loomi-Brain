# Operations Runbook

Reader: owner/operator responsible for local, private, or cloud Loomi-Brain operations.

Post-read action: start, verify, back up, update, roll back, and triage the system.

## Start Local

```bash
cp .env.example .env
make setup
docker compose -f infra/docker/compose.yml up --build -d postgres redis api worker web
```

Optional profiles:

```bash
docker compose -f infra/docker/compose.yml --profile storage up -d object-store
docker compose -f infra/docker/compose.yml --profile scan up -d clamav
docker compose -f infra/docker/compose.yml --profile observability up -d observability
docker compose -f infra/docker/compose.yml --profile llm up -d vllm
```

## Health Checks

```bash
curl -fsS http://127.0.0.1:8000/health/live
curl -fsS http://127.0.0.1:8000/health/ready
curl -fsSI http://127.0.0.1:3000/
docker compose -f infra/docker/compose.yml ps
```

## Migrations

```bash
docker compose -f infra/docker/compose.yml exec api alembic upgrade head
```

Run migrations before starting a new API version in cloud/private deployments. Keep a PostgreSQL backup before schema changes.

## Backups

```bash
scripts/backup-postgres.sh
scripts/backup-objects.sh
scripts/disaster-recovery-smoke.sh
```

## Rollback

1. Stop API and worker.
2. Restore the previous image tag or release artifact.
3. If a migration changed schema, restore from the pre-migration backup unless the migration is explicitly reversible and tested.
4. Start API and worker.
5. Verify readiness, login, search, chat, agent run creation, MCP test invocation, and observability.

## Outage Triage

- API not ready: check database health, migration status, environment validation, and API logs.
- Database unavailable: stop writes, take a snapshot if possible, inspect disk, connections, and managed provider status.
- Object storage unavailable: pause ingestion and restore storage before retries.
- Provider outage: switch to mock/local provider for demo mode or another configured server-side provider.
- Telemetry outage: product requests should continue; verify exporter configuration and retention.
- Worker stalled: restart worker, inspect failed jobs, and avoid duplicate side effects by preserving idempotency keys.

## Scaling Notes

- Keep API workers behind a shared database and shared rate limiter before horizontal scaling.
- Keep background workers bounded by job concurrency, parser limits, model budgets, and object-store throughput.
- Do not run persistent Python workers as Vercel serverless functions.
