# CI Control Plane — task runner (https://just.systems)
# `just` lists recipes. Variables come from the environment or .env (e.g. PORT=8077).

set dotenv-load

py := "backend/.venv/bin/python"
port := env("PORT", "8000")
api := "http://127.0.0.1:" + port
export KUBECONFORM_CACHE := env("KUBECONFORM_CACHE", justfile_directory() / "var/kubeconform-cache")

# List recipes
default:
    @just --list --unsorted

# Install backend (uv) and frontend (pnpm) dependencies
install:
    cd backend && uv sync --python 3.12
    cd frontend && pnpm install

# Build the dashboard into frontend/dist (served by the API)
build-ui:
    cd frontend && pnpm build

# Run API + worker + built dashboard on 127.0.0.1:$PORT (default 8000)
dev:
    cd backend && uv run uvicorn app.main:app --host 127.0.0.1 --port {{port}}

# Run the Vite dev server on :5173 (proxies /api to the backend)
dev-ui:
    cd frontend && RCP_BACKEND_URL={{api}} pnpm dev

# Run the worker as a separate process (start the API with RUN_WORKER=false)
worker:
    cd backend && uv run python -m app.worker

# Backend + frontend tests
test:
    cd backend && uv run pytest -q
    cd frontend && pnpm test

# Lint everything
lint:
    cd backend && uv run ruff check app tests ../.claude/hooks ../.claude/skills ../demo/scripts ../scripts
    cd frontend && pnpm lint

# Run the chart validator on demo/charts
validate:
    {{py}} .claude/skills/k8s-failure-analysis/scripts/validate.py demo/charts

# Prove every scenario fails for its intended reason
scenarios:
    {{py}} demo/scripts/scenario.py verify all

# Prepare a scenario branch and print the gh pr create command: just scenario C [base]
scenario id base="main":
    {{py}} demo/scripts/scenario.py prepare {{id}} --base {{base}}

# Rehearse analysis + remediation agents locally, no GitHub: just dry-run C
dry-run id="C":
    {{py}} demo/scripts/agent_dry_run.py {{id}}

# Verify binaries, credentials, integrations, service health (add --live / --slack)
preflight *flags:
    python3 scripts/preflight.py {{flags}}

# Automation preset: analyze + remediate + push automatically (workshop mode)
autonomous:
    @curl -s -X PUT {{api}}/api/settings/automation -H 'content-type: application/json' \
      -d '{"auto_analyze":true,"auto_remediate":true,"auto_push":true}'; echo

# Automation preset: push requires approval (safe default)
safe:
    @curl -s -X PUT {{api}}/api/settings/automation -H 'content-type: application/json' \
      -d '{"auto_analyze":true,"auto_remediate":true,"auto_push":false}'; echo

# Close all demo PRs and delete their branches
reset-prs:
    gh pr list --search "head:demo/" --json number -q '.[].number' | xargs -n1 -I{} gh pr close {} --delete-branch

# Delete the local database (tasks / history)
reset-db:
    rm -f var/rcp.db var/rcp.db-wal var/rcp.db-shm
