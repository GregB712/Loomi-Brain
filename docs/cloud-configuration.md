# Cloud Configuration

Phase 3 cloud deployment keeps the same server-side boundaries as local mode.

## Required

- PostgreSQL with pgvector enabled.
- Migrations applied through Alembic.
- Secure owner password and secure cookies.
- Real malware scanner when accepting remote uploads.
- Provider keys stored as server-side secrets, not frontend environment variables.

## Recommended Environment

```text
LOOMI_ENVIRONMENT=production
LOOMI_SESSION_COOKIE_SECURE=true
LOOMI_SCANNER_REQUIRED=true
LOOMI_CHAT_PROVIDER=openai-compatible
LOOMI_CHAT_MODEL=<approved-model>
LOOMI_OBSERVABILITY_ENABLED=true
LOOMI_OBSERVABILITY_EXPORTER=otlp_http
LOOMI_OBSERVABILITY_EXPORTER_ENDPOINT=<collector-or-langfuse-otlp-endpoint>
LOOMI_OBSERVABILITY_LOCAL_ONLY=false
LOOMI_OBSERVABILITY_SAMPLE_RATE=0.1
LOOMI_OBSERVABILITY_CONTENT_CAPTURE=none
LOOMI_OBSERVABILITY_RETENTION_DAYS=14
LOOMI_OPENAI_COMPATIBLE_BASE_URL=<server-side-url>
LOOMI_OPENAI_COMPATIBLE_API_KEY=<secret>
```

Do not configure provider keys with `NEXT_PUBLIC_`. The web app only receives provider/model metadata and streamed response events from the API.

Production rejects observability content capture other than `none` and sampling above
25%. Provider keys, cookies, CSRF/session tokens, signed URLs, document binaries,
unrestricted document text, and tool secrets must not be sent to logs, telemetry, or
browser-visible configuration.
