FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder

WORKDIR /app/apps/worker

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

COPY apps/worker/pyproject.toml apps/worker/uv.lock ./
RUN uv sync --frozen --no-dev

FROM python:3.14-slim-bookworm AS runtime

ENV PATH="/app/apps/worker/.venv/bin:${PATH}"
ENV PYTHONPATH="/app/apps/worker/src"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN groupadd --system loomi && useradd --system --gid loomi --home-dir /app --shell /usr/sbin/nologin loomi

WORKDIR /app/apps/worker

COPY --from=builder /app/apps/worker/.venv ./.venv
COPY apps/worker/src ./src

RUN chown -R loomi:loomi /app

USER loomi

CMD ["python", "-m", "loomi_worker.main", "serve"]
