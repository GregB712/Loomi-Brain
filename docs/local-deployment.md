# Local Deployment

## Start

```bash
make setup
make dev
```

Open the web app at `http://127.0.0.1:3000`, the Knowledge Library at `http://127.0.0.1:3000/knowledge`, search at `http://127.0.0.1:3000/search`, and cited chat at `http://127.0.0.1:3000/chat`.

Local owner credentials:

```text
Email: owner@loomi.local
Password: loomi-local-owner-password
```

## Services

Default Compose services are PostgreSQL with pgvector, Redis, API, worker, and web. The API persists uploaded source objects in the `loomi-api-objects` volume at `/app/apps/api/var/private-objects`.

Optional profiles:

```bash
docker compose -f infra/docker/compose.yml --profile storage up -d object-store
docker compose -f infra/docker/compose.yml --profile scan up -d clamav
docker compose -f infra/docker/compose.yml --profile observability up -d observability
```

The Phase 2 request path uses the local object store adapter and fake scanner by default. Phase 3 chat uses the deterministic mock provider by default, so no paid provider credentials are required. MinIO and ClamAV containers are present for later adapter work.

## Ingestion Configuration

Relevant settings are documented in `.env.example`:

- `LOOMI_STORAGE_ROOT`
- `LOOMI_MAX_UPLOAD_BYTES`
- `LOOMI_MAX_UPLOAD_FILES`
- `LOOMI_SCANNER_MODE`
- `LOOMI_SCANNER_REQUIRED`
- `LOOMI_EXTRACTION_ENGINE`
- `LOOMI_EMBEDDING_MODEL`
- `LOOMI_CHAT_PROVIDER`
- `LOOMI_CHAT_MODEL`
- `LOOMI_OPENAI_COMPATIBLE_BASE_URL`
- `LOOMI_VLLM_BASE_URL`

Use `LOOMI_EXTRACTION_ENGINE=docling` only after installing the optional API extra:

```bash
cd apps/api
uv sync --extra docling
```

Use `LOOMI_CHAT_PROVIDER=vllm` and `LOOMI_VLLM_BASE_URL=<local OpenAI-compatible URL>` to test a local vLLM server.

## Stop

```bash
make down
```

Named Docker volumes are intentionally preserved. Remove them manually only when you want to discard local database and source-object data.
