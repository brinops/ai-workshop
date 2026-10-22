.DEFAULT_GOAL := help
SHELL := /bin/bash
PY := backend/.venv/bin/python
export KUBECONFORM_CACHE ?= $(CURDIR)/var/kubeconform-cache

help: ## Show targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Install backend (uv) and frontend (pnpm) dependencies
	cd backend && uv sync --python 3.12
	cd frontend && pnpm install

build-ui: ## Build the dashboard into frontend/dist (served by the API on :8000)
	cd frontend && pnpm build

dev: ## Run API + worker on :8000 (serves the built UI)
	cd backend && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

dev-ui: ## Run the Vite dev server on :5173 (proxies /api to :8000)
	cd frontend && pnpm dev

worker: ## Run the worker as a separate process (start the API with RUN_WORKER=false)
	cd backend && uv run python -m app.worker

test: ## Backend + frontend tests
	cd backend && uv run pytest -q
	cd frontend && pnpm test

lint: ## Lint everything
	cd backend && uv run ruff check app tests ../.claude/hooks ../tools ../demo/scripts ../scripts
	cd frontend && pnpm lint

validate: ## Run the chart validator on demo/charts
	$(PY) tools/chart_validator/validate.py demo/charts

scenarios: ## Prove every scenario fails for its intended reason
	$(PY) demo/scripts/scenario.py verify all

scenario: ## Prepare a scenario branch: make scenario S=A [BASE=main]
	$(PY) demo/scripts/scenario.py prepare $(S) --base $(or $(BASE),main)

dry-run: ## Rehearse analysis + remediation agents locally (no GitHub): make dry-run S=C
	$(PY) demo/scripts/agent_dry_run.py $(S)

preflight: ## Verify binaries, credentials, integrations, service health
	python3 scripts/preflight.py

autonomous: ## Switch automation to fully autonomous (workshop mode)
	curl -s -X PUT localhost:8000/api/settings/automation -H 'content-type: application/json' \
	  -d '{"auto_analyze":true,"auto_remediate":true,"auto_push":true}'; echo

safe: ## Switch automation to safe mode (push requires approval)
	curl -s -X PUT localhost:8000/api/settings/automation -H 'content-type: application/json' \
	  -d '{"auto_analyze":true,"auto_remediate":true,"auto_push":false}'; echo

reset-db: ## Delete the local database (tasks/history)
	rm -f var/rcp.db var/rcp.db-wal var/rcp.db-shm

.PHONY: help install build-ui dev dev-ui worker test lint validate scenarios scenario dry-run preflight autonomous safe reset-db
