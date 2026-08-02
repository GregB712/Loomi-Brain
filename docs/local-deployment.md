# Local Deployment

Reader: reviewer or owner running Loomi-Brain on one machine.

Post-read action: start a secure local stack, choose optional profiles, and know what is demo-only.

## Default Stack

```bash
cp .env.example .env
make setup
docker compose -f infra/docker/compose.yml up --build -d postgres redis api worker web
```

Open `http://127.0.0.1:3000`.

Development-only owner:

```text
Email: owner@loomi.local
Password: loomi-local-owner-password
```

The default Compose profile binds service ports to localhost. App containers run as non-root users, drop Linux capabilities, use no-new-privileges, have read-only root filesystems where practical, and use named volumes for database and private objects.

## Optional Profiles

```bash
docker compose -f infra/docker/compose.yml --profile storage up -d object-store
docker compose -f infra/docker/compose.yml --profile scan up -d clamav
docker compose -f infra/docker/compose.yml --profile observability up -d observability
docker compose -f infra/docker/compose.yml --profile llm up -d vllm
```

Optional images are configurable in `.env` so operators can pin organization-approved tags or digests.

## Migrations And Seed

The API container runs migrations and seeds the local owner at startup. Outside Docker:

```bash
make migrate
make seed
```

## Local Model Profiles

CPU-only demo:

- Keep `LOOMI_CHAT_PROVIDER=mock`.
- No provider key required.
- Deterministic output is suitable for CI and screenshots.

Low-VRAM local endpoint:

- Run an OpenAI-compatible local server outside the app stack.
- Set `LOOMI_CHAT_PROVIDER=openai-compatible`.
- Set `LOOMI_OPENAI_COMPATIBLE_BASE_URL` and server-side API key if required.
- Verify first-token latency and memory pressure manually.

Moderate-VRAM vLLM:

- Start the optional `llm` profile only on a machine with suitable GPU/driver support.
- Set `LOOMI_VLLM_MODEL` to a model your hardware can load.
- Set `LOOMI_CHAT_PROVIDER=vllm` and `LOOMI_VLLM_BASE_URL=http://vllm:8000/v1` for API-to-vLLM traffic inside Compose.

Do not assume every model works on every machine. Record model name, quantization, GPU memory, CPU RAM, and latency when reporting results.

## Backup And Teardown

```bash
scripts/backup-postgres.sh
scripts/backup-objects.sh
scripts/disaster-recovery-smoke.sh
docker compose -f infra/docker/compose.yml down
```

Named volumes are preserved by default. Delete volumes only when intentionally discarding local data.
