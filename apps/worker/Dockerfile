FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /app/apps/worker

COPY apps/worker/pyproject.toml apps/worker/uv.lock ./
RUN uv sync --frozen --no-dev

COPY apps/worker/src ./src

ENV PATH="/app/apps/worker/.venv/bin:${PATH}"
ENV PYTHONPATH="/app/apps/worker/src"

CMD ["uv", "run", "--frozen", "--no-dev", "python", "-m", "loomi_worker.main", "serve"]
