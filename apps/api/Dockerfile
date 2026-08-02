FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder

WORKDIR /app/apps/api

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN uv sync --frozen --no-dev

FROM python:3.14-slim-bookworm AS runtime

ENV PATH="/app/apps/api/.venv/bin:${PATH}"
ENV PYTHONPATH="/app/apps/api/src"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN groupadd --system loomi && useradd --system --gid loomi --home-dir /app --shell /usr/sbin/nologin loomi

WORKDIR /app/apps/api

COPY --from=builder /app/apps/api/.venv ./.venv
COPY apps/api/alembic.ini ./alembic.ini
COPY apps/api/migrations ./migrations
COPY apps/api/src ./src

RUN mkdir -p /app/apps/api/var/private-objects && chown -R loomi:loomi /app

USER loomi

EXPOSE 8000

CMD ["python", "-m", "fastapi", "run", "src/loomi_api/main.py", "--host", "0.0.0.0", "--port", "8000"]
