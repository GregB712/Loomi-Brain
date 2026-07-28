PNPM ?= corepack pnpm
UV ?= uv

.PHONY: setup dev test lint typecheck format security migrate seed eval demo down

setup:
	corepack enable
	$(PNPM) install --frozen-lockfile
	cd apps/api && $(UV) sync --frozen
	cd apps/worker && $(UV) sync --frozen

dev:
	docker compose -f infra/docker/compose.yml up --build -d postgres redis api worker web

test:
	cd apps/api && $(UV) run pytest
	cd apps/worker && $(UV) run pytest
	$(PNPM) test

lint:
	cd apps/api && $(UV) run ruff check .
	cd apps/worker && $(UV) run ruff check .
	$(PNPM) lint

typecheck:
	cd apps/api && $(UV) run mypy src tests
	cd apps/worker && $(UV) run mypy src tests
	$(PNPM) typecheck

format:
	cd apps/api && $(UV) run ruff format .
	cd apps/worker && $(UV) run ruff format .
	$(PNPM) format

security:
	bash scripts/security-check.sh

migrate:
	cd apps/api && $(UV) run alembic upgrade head

seed:
	cd apps/api && $(UV) run python -m loomi_api.seed

eval:
	cd apps/api && PYTHONPATH=src $(UV) run python -m loomi_api.evaluation.run

demo:
	@echo "Demo mode starts after ingestion and mock LLM slices land."

down:
	docker compose -f infra/docker/compose.yml down
