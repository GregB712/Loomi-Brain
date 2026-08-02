# Cloud Configuration

Reader: owner preparing a cloud deployment.

Post-read action: map Loomi-Brain to managed services without weakening the owner-only boundary.

## Reference Architecture

- Frontend: Vercel.
- API and worker: long-running container platform such as Fly.io, Render, Railway, ECS, Cloud Run jobs/services, or a VM orchestrated by the owner.
- Database: Neon PostgreSQL with pgvector.
- Object storage: private S3-compatible bucket.
- Observability: managed OTLP/Langfuse-compatible endpoint or self-hosted collector.
- Models: cloud LLM provider or a secured OpenAI-compatible endpoint.

Do not deploy persistent Python workers as Vercel serverless functions.

## Required Environment

```text
LOOMI_ENVIRONMENT=production
LOOMI_SESSION_COOKIE_SECURE=true
LOOMI_SCANNER_REQUIRED=true
LOOMI_CORS_ORIGINS=["https://<web-domain>"]
LOOMI_TRUSTED_HOSTS=["<api-domain>"]
LOOMI_OWNER_EMAIL=<exact-owner-email>
LOOMI_OWNER_PASSWORD=<secret-reference>
LOOMI_DATABASE_URL=<pooled-neon-url>
LOOMI_STORAGE_ROOT=<private-object-adapter-root-or-mount>
LOOMI_CHAT_PROVIDER=openai-compatible
LOOMI_CHAT_MODEL=<approved-model>
LOOMI_OPENAI_COMPATIBLE_BASE_URL=<server-side-url>
LOOMI_OPENAI_COMPATIBLE_API_KEY=<secret-reference>
LOOMI_OBSERVABILITY_ENABLED=true
LOOMI_OBSERVABILITY_EXPORTER=otlp_http
LOOMI_OBSERVABILITY_EXPORTER_ENDPOINT=<collector-endpoint>
LOOMI_OBSERVABILITY_LOCAL_ONLY=false
LOOMI_OBSERVABILITY_SAMPLE_RATE=0.1
LOOMI_OBSERVABILITY_CONTENT_CAPTURE=none
LOOMI_MCP_ALLOW_PRIVATE_NETWORKS=false
```

Provider keys must never use `NEXT_PUBLIC_` variables.

## Neon Notes

- Use pooled connections for request traffic.
- Use a direct connection for migrations when Neon recommends it.
- Keep connection limits below the plan maximum.
- Run Alembic migrations as a release step before starting new API/worker versions.
- Back up before migrations and document rollback.

## CORS, Cookies, And TLS

- Allow only the deployed web origin.
- Set trusted hosts to the API domain.
- Use HTTPS-only cookies in production.
- Keep API and web domains stable before login testing.
- Validate redirects strictly if adding OAuth later.

## Storage

- Keep buckets private.
- Prefer short-lived signed URLs for direct object access.
- Do not serve private source objects from the frontend host.
- Configure lifecycle retention intentionally.
- Track provider egress costs for retrieval, export, and backup.

## Worker Scaling

- Scale workers separately from API containers.
- Bound concurrency by parser limits, database connections, provider budgets, and object-store throughput.
- Preserve idempotency keys for retries.
- Keep failed-job/dead-letter handling visible in operations docs before production use.

## Rollback

1. Stop new writes if data integrity is suspect.
2. Restore the previous API/worker image tag.
3. Restore database from backup if schema/data migration is not safely reversible.
4. Verify health, login, ingestion, search, chat, agent approvals, MCP test server, skills, and observability.

## Cost Categories

- Vercel frontend hosting.
- API/worker containers.
- Neon compute/storage/branching/egress.
- Object storage and egress.
- Malware scanning resources.
- Observability ingest and retention.
- LLM provider tokens or private inference hardware.
- Backup storage.

Free tiers are useful for demos but may sleep, throttle, lack restore guarantees, or impose connection limits.
