# Career Coach — developer task runner.
#
# Every recipe shells out to cross-platform executables (uv, docker, alembic),
# so the same Makefile works on Windows (cmd.exe), macOS, and Linux.
# See the README for how to install `make` on Windows.

.DEFAULT_GOAL := help

.PHONY: help install db-up db-down db-logs migrate migration setup run run-uvicorn test test-integration db-reset

help: ## Show this help.
	@echo Career Coach - available commands:
	@echo   make setup        First-time setup - deps, database, migrations
	@echo   make install      Install Python dependencies via uv sync
	@echo   make db-up        Start the PostgreSQL pgvector container
	@echo   make db-down      Stop the database container
	@echo   make db-logs      Tail the database container logs
	@echo   make migrate      Apply all Alembic migrations
	@echo   make migration    New migration - usage: make migration name=msg
	@echo   make run          Start the API on Windows - selector event loop
	@echo   make run-uvicorn  Start the API via uvicorn CLI for macOS/Linux
	@echo   make test         Run the test suite
	@echo   make db-reset     Drop and recreate the schema, then re-stamp Alembic

install: ## Install Python dependencies.
	uv sync

db-up: ## Start the database container in the background.
	docker compose up -d

db-down: ## Stop the database container.
	docker compose down

db-logs: ## Tail the database container logs.
	docker compose logs -f db

migrate: ## Apply all pending Alembic migrations.
	uv run alembic upgrade head

migration: ## Autogenerate a new migration. Usage: make migration name="add foo"
	uv run alembic revision --autogenerate -m "$(name)"

setup: ## First-time setup: install deps, start the DB, wait, run migrations.
	uv sync
	docker compose up -d
	@echo Waiting for PostgreSQL to accept connections...
	uv run python -c "import time; time.sleep(5)"
	uv run alembic upgrade head
	@echo Setup complete. Start the API with: make run

# On Windows the uvicorn CLI binds a ProactorEventLoop before app.main is
# imported, which the psycopg3 async driver cannot use. Running the module
# directly lets app.main inject a SelectorEventLoop (see app/main.py).
run: ## Start the API locally on Windows.
	uv run python -m app.main

run-uvicorn: ## Start the API via the uvicorn CLI (macOS/Linux).
	uv run uvicorn app.main:app --reload --port 8000

test: ## Run the test suite (excludes integration tests needing a live LLM proxy).
	uv run pytest -m "not integration"

test-integration: ## Run only the integration tests (requires real LITELLM_* in .env).
	uv run pytest -m integration

db-reset: ## Drop the schema and rebuild it from the Alembic migrations.
	uv run python -m scripts.reset_db
