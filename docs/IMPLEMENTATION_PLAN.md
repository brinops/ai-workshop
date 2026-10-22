# Implementation Plan

## Phase 0 — Inspection (done)

* Repository: empty (`main` without commits), remote `brinops/ai-workshop` (private, admin access).
* Local tools: Python 3.12, uv, Node 26 + pnpm, Helm v4.2, kubeconform 0.8 (installed), gh 2.97 (authenticated),
  Claude Code 2.1.x (headless `-p`, `--json-schema` → `structured_output`, `--agent`, `--allowed-tools`,
  `--permission-mode dontAsk`, `--max-budget-usd`, `--output-format stream-json`), Docker.
* Slack webhook: not configured on this machine — implemented, verification pending credentials.

## Decisions

| Decision | Why |
|---|---|
| In-process asyncio worker instead of APScheduler | One moving part, no extra scheduler state; coordination lives in SQLite leases so a standalone worker is also possible |
| SSE over WebSockets | One-directional, survives proxies, trivial reconnect with `Last-Event-ID` |
| Backend (not the agent) commits and pushes | Least privilege: the agent never gets git/network access; scope is verified on the diff before any push |
| One validator for CI, backend and agent | Local and remote validation cannot drift; deterministic categories come from one place |
| Agents loaded from operator checkout, PR mounted via `--add-dir` | A malicious PR cannot rewrite the skill/agent definitions |
| Hand-written shadcn-style components on Radix | Same look and accessibility as shadcn/ui without the generator step |
| Primary run mode is local (`make dev`); Docker Compose provided | Claude Code OAuth lives in the macOS keychain; containers need `ANTHROPIC_API_KEY`/`CLAUDE_CODE_OAUTH_TOKEN` |

## Phase 1 — Backend foundation
SQLAlchemy models + Alembic migration, settings, state machine with transition table, registration service
(idempotent), events/comments, task API, worker loop with leases/heartbeat/recovery, SSE.

## Phase 2 — Dashboard
Vite + React + TS + Tailwind v4; Kanban, task drawer (overview, timeline, diagnosis, diff, logs, CI, Slack),
automation toggles, manual controls, health bar, presentation mode, SSE live updates.

## Phase 3 — GitHub + Claude Code
Hook, GitHub client (PR, check-runs, job logs, annotations), worktree manager, Claude runner (stream-json,
process group, timeout, cancellation), analysis skill + reconciliation, remediation subagent + scope check, push.

## Phase 4 — Validation + Slack
`tools/chart_validator` (YAML parse, helm lint, helm template, kubeconform, consistency checks),
`.github/workflows/helm-validate.yaml`, Slack Block Kit notifications with persisted delivery status.

## Phase 5 — Workshop
`demo/charts/payments-api`, scenarios A/B/C (`demo/scripts/scenario.sh`), preflight, runbook, E2E run.

## Test matrix
Registration/dedup · transitions · scheduler dispatch · CI aggregation · analysis validation/reconciliation ·
remediation scope · retry limits · lease recovery · API endpoints · scenario validators (real helm/kubeconform).
