# AI Remediation Control Plane

A working, end-to-end demonstration of autonomous remediation of broken Kubernetes / Helm configuration:

**Detection → Reasoning → Autonomous Repair → Deterministic Validation → Human Visibility**

A developer opens a PR from Claude Code → a Claude Code **hook** registers it → a worker watches the real
**GitHub Actions** check → on failure a headless Claude Code **Analysis Skill** diagnoses it → a Claude Code
**Remediation Subagent** fixes it in an isolated worktree → the control plane re-validates, commits and pushes to the
same PR → GitHub Actions re-runs → the task moves to **DONE** and **Slack** receives a summary. Every step is
visible live on a Kanban dashboard.

- How it works, step by step (what is written to the DB, who decides what): [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md)
- Architecture & security boundaries: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Workshop runbook (step-by-step live demo): [docs/RUNBOOK.md](docs/RUNBOOK.md)
- Troubleshooting: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
- Implementation plan & decisions: [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md)

## Architecture

```mermaid
flowchart LR
    dev([Developer · Claude Code]) -- "gh pr create" --> PR[(GitHub PR)]
    dev -. "PostToolUse hook" .-> API
    PR -- "pull_request" --> GHA[GitHub Actions<br/>helm-validate]
    PR -. "webhook (optional)" .-> API
    subgraph CP[Control plane · FastAPI + SQLite WAL]
      API[REST + SSE] --- DB[(tasks · events · runs)]
      W[Worker · leases · retries] --- DB
    end
    W -- "check runs + job logs" --> GHA
    W -- "claude -p · skill" --> AN[Analysis Skill]
    W -- "claude -p --agent" --> RE[Remediation Subagent]
    W -- "fast-forward push" --> PR
    W -- "webhook" --> SL[(Slack)]
    UI[Dashboard] -- "REST + SSE" --> API
```

### Task state machine

```mermaid
stateDiagram-v2
    [*] --> NEW
    NEW --> WAITING_CI
    WAITING_CI --> DONE: checks green (no remediation)
    WAITING_CI --> ANALYZING: required check failed
    ANALYZING --> TODO: remediable diagnosis
    ANALYZING --> NEEDS_REVIEW: non-remediable / low confidence
    TODO --> IN_PROGRESS: Auto Remediate / Start Remediation
    IN_PROGRESS --> VALIDATING: fix pushed (Auto Push / Approve Push)
    IN_PROGRESS --> NEEDS_REVIEW: scope or local validation failed
    VALIDATING --> DONE: checks green on fix commit
    VALIDATING --> ANALYZING: still failing, attempts left
    VALIDATING --> NEEDS_REVIEW: attempts exhausted
    NEEDS_REVIEW --> WAITING_CI: Retry
    FAILED --> WAITING_CI: Retry
```

Kanban columns: **NEW** (NEW, WAITING_CI, ANALYZING) · **TODO** (TODO, NEEDS_REVIEW) ·
**IN PROGRESS** (IN_PROGRESS, VALIDATING) · **DONE** (DONE, FAILED). Cancel moves any active task to FAILED.

## Repository layout

```text
backend/                FastAPI app, worker, SQLAlchemy models, Alembic migrations, pytest suite
  app/api/              REST, SSE stream, GitHub webhook
  app/orchestration/    state machine, worker (leases, recovery, stages), CI aggregation
  app/agents/           analysis & remediation contracts (schemas, prompts, reconciliation, scope)
  app/integrations/     GitHub REST, git worktrees, headless Claude runner, Slack
frontend/               React + TypeScript + Vite + Tailwind dashboard
tools/chart_validator/  deterministic validator — used by CI, the backend and the agent
demo/charts/            payments-api Helm chart
demo/scenarios/         scenario definitions A/B/C
demo/scripts/           scenario.py (prepare/verify), agent_dry_run.py (rehearsal)
.claude/hooks/          register_pr.py — PostToolUse hook
.claude/skills/         k8s-failure-analysis — Analysis Skill
.claude/agents/         k8s-remediator — Remediation Subagent
.github/workflows/      helm-validate (required check), ci (tests)
scripts/preflight.py    environment & integration preflight
```

## Quick start (local — recommended)

Requirements: [just](https://just.systems), Python 3.12 + [uv](https://docs.astral.sh/uv/), Node 22+ + pnpm, git, `gh`, `helm`, `kubeconform`,
Claude Code (`claude`) logged in.

```bash
brew install just helm kubeconform gh uv pnpm   # macOS
cp .env.example .env                          # set SLACK_WEBHOOK_URL
just install                                  # uv sync + pnpm install
just build-ui                                 # dashboard → frontend/dist
just dev                                      # API + worker + UI on http://localhost:8000
just preflight                                # in another terminal
```

Run `just` to list all recipes. Set `PORT` in `.env` if :8000 is taken (also set `PUBLIC_URL` to match —
the hook posts there). UI development with hot reload: `just dev` + `just dev-ui` → http://localhost:5173.

### Docker Compose

```bash
cp .env.example .env   # + GITHUB_TOKEN, SLACK_WEBHOOK_URL, ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN
docker compose up --build
```

The container cannot reach the macOS keychain, so it needs an explicit Claude credential and a GitHub token
(git pushes over HTTPS with that token).

## Authentication & configuration

| Integration | What is needed | How it is used |
|---|---|---|
| GitHub API | `gh auth login` (or `GITHUB_TOKEN` with `repo` scope) | read PRs, check runs, job logs, annotations |
| git push | SSH key / credential helper that can push to the PR branch | the backend pushes the fix commit (fast-forward only) |
| Claude Code | `claude` logged in (OAuth), or `ANTHROPIC_API_KEY` / `CLAUDE_CODE_OAUTH_TOKEN` | headless analysis and remediation |
| Slack | an [Incoming Webhook](https://api.slack.com/messaging/webhooks) URL in `SLACK_WEBHOOK_URL` | success / review / failure notifications |

All variables are documented in [`.env.example`](.env.example). Key ones:

| Variable | Default | Meaning |
|---|---|---|
| `REQUIRED_CHECKS` | `["helm-validate"]` | check runs that must succeed on the exact SHA |
| `REMEDIATION_ALLOWED_PATHS` | `["demo/charts/**"]` | the only paths the agent may edit / the diff may touch |
| `MAX_REMEDIATION_ATTEMPTS` | `2` | bounded fix → CI → re-analyze loops |
| `CLAUDE_MODEL` | `sonnet` | model for both agents |
| `AGENT_MAX_BUDGET_USD` | `2.0` | per-run spend cap (`--max-budget-usd`) |
| `DEFAULT_AUTO_PUSH` | `false` | safe default: pushing requires approval |
| `RCP_API_TOKEN` | — | optional bearer token for `/api/tasks/register` |
| `GITHUB_WEBHOOK_SECRET` | — | enables `/api/webhooks/github` |
| `ALLOWED_REPOS` | `[]` | restrict which repositories can be registered |

### Hook installation

The hook ships in [`.claude/settings.json`](.claude/settings.json) and is active for any Claude Code session
started in this repository:

```json
{ "hooks": { "PostToolUse": [ { "matcher": "Bash",
  "hooks": [ { "type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/register_pr.py\"", "timeout": 45 } ] } ] } }
```

* It acts only when the Bash command contains `gh pr create` and a PR can be confirmed via `gh pr view`.
* It posts to `RCP_API_URL` (default `http://localhost:8000`); the optional token comes from `RCP_API_TOKEN` in the
  environment — never from the config file.
* If the backend is down the registration is spooled to `~/.cache/rcp/pending-registrations.jsonl` and retried on the
  next PR creation, or manually: `python3 .claude/hooks/register_pr.py --flush`.
* Register any existing PR manually: `python3 .claude/hooks/register_pr.py --register <PR URL>`.
* To use the hook in another repository, copy `.claude/hooks/register_pr.py` and the `hooks` block into that
  repository's `.claude/settings.json` (or `~/.claude/settings.json` for all projects).

Run `/hooks` inside Claude Code to confirm it is loaded.

### Automation controls

| Setting | Off | On |
|---|---|---|
| Auto Analyze | failed PR waits for **Analyze Now** | analysis starts when CI fails |
| Auto Remediate | diagnosis waits for **Start Remediation** | remediation starts after a remediable diagnosis |
| Auto Push | validated fix waits for **Approve Push** (default) | fix is pushed immediately |

`just autonomous` / `just safe` switch presets from the terminal; the dashboard has the same toggles.
The control plane **never merges** a PR.

## Demo scenarios

| ID | Error injected | Caught by | Expected class |
|---|---|---|---|
| A | mis-indented `memory:` under `resources.limits` in `values.yaml` | YAML parse | `SYNTAX_ERROR` |
| B | `replicaCount: three` | kubeconform (`spec.replicas` must be integer) | `SCHEMA_VIOLATION` |
| C | `service.targetPort: 9090` while the app listens on `app.port: 8080` | consistency check | `LOGICAL_CONFIGURATION_ERROR` |

```bash
just scenarios            # proves each scenario fails for the intended reason (and only that reason)
just scenario C         # new branch from origin/main + error + push; prints the gh pr create command
just dry-run C          # rehearse both agents locally without GitHub (costs ~$0.40)
```

Each run creates a fresh, timestamped branch, so scenarios are independently repeatable.

## Testing

```bash
just test     # backend pytest (fakes for GitHub/agents/Slack + real helm/kubeconform) and frontend vitest
just lint
```

## Safety summary

* Agents run headless with `--permission-mode dontAsk` and explicit allowlists — no permission bypass.
* Analysis: `Read, Grep, Glob` only. Remediation: `Edit` restricted to `<worktree>/demo/charts/**` and one Bash
  command (the trusted validator). No git, network, or other shell access. Verified by a live negative test.
* Skills/agents are loaded from the operator's checkout, not from the PR under analysis.
* PR text, file contents and CI logs are passed as untrusted data; secrets are scrubbed from the agent
  environment and redacted from logs, events, comments and Slack payloads.
* The backend re-checks the diff scope and re-runs validation before committing; pushes are fast-forward only,
  verified against the expected SHA, and refused for protected branches.
