FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /app/apps/api

COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN uv sync --frozen --no-dev

COPY apps/api/alembic.ini ./alembic.ini
COPY apps/api/migrations ./migrations
COPY apps/api/src ./src

ENV PATH="/app/apps/api/.venv/bin:${PATH}"
ENV PYTHONPATH="/app/apps/api/src"
EXPOSE 8000

CMD ["uv", "run", "--frozen", "--no-dev", "fastapi", "run", "src/loomi_api/main.py", "--host", "0.0.0.0", "--port", "8000"]
