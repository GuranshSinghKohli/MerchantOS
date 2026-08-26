.PHONY: deps up down test lint fmt typecheck api worker web migrate

deps:
	uv sync --all-packages --group dev
	pnpm install

up:
	docker compose -f infra/docker/compose.yml up -d --wait

down:
	docker compose -f infra/docker/compose.yml down

migrate:
	cd packages/db && uv run alembic upgrade head

test:
	bash -lc 'set -a; [ -f .env ] && . ./.env; set +a; uv run pytest'
	pnpm web:test

lint:
	uv run ruff check .
	pnpm web:lint

fmt:
	uv run ruff format .
	uv run ruff check --fix .

typecheck:
	uv run mypy
	pnpm web:typecheck

api:
	uv run --package merchantos-api uvicorn merchantos_api.main:app --reload --host 0.0.0.0 --port 8000

worker:
	uv run --package merchantos-worker python -m merchantos_worker

web:
	pnpm web
