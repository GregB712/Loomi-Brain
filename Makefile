PNPM ?= corepack pnpm
UV ?= uv

.PHONY: setup dev test lint typecheck format security migrate seed eval demo down

setup:
	corepack enable
	$(PNPM) install
	$(UV) sync --project apps/api
	$(UV) sync --project apps/worker

dev:
	@echo "Run web, API, and worker in separate terminals until the dev orchestrator is added:"
	@echo "  $(PNPM) --filter @loomi/web dev"
	@echo "  cd apps/api && $(UV) run fastapi dev src/loomi_api/main.py"
	@echo "  cd apps/worker && $(UV) run python -m loomi_worker.main"

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
	@echo "Security scanners will be wired after lockfiles and CI are generated."

migrate:
	@echo "Alembic migrations start in the next Phase 1 slice."

seed:
	@echo "Synthetic seed data starts after the initial schema lands."

eval:
	@echo "Evaluation harness starts in Phase 5."

demo:
	@echo "Demo mode starts after ingestion and mock LLM slices land."

down:
	docker compose -f infra/docker/compose.yml down
