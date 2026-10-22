# Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `make preflight` → worker ✗ "no heartbeat" | API started with `RUN_WORKER=false` and no separate worker | `make worker`, or unset `RUN_WORKER` |
| Hook prints nothing after `gh pr create` | hook not loaded (session started before `.claude/settings.json` existed) | restart Claude Code in the repo; check `/hooks` |
| Hook: "backend unreachable … queued" | API not running | `make dev`, then `python3 .claude/hooks/register_pr.py --flush` |
| Hook: "backend rejected registration (HTTP 401)" | `RCP_API_TOKEN` set on the server but not in the shell running Claude Code | export the same `RCP_API_TOKEN` before starting `claude` |
| Registration HTTP 502 | backend cannot confirm the PR on GitHub | `gh auth status`; set `GITHUB_TOKEN`; check repo access |
| Task stuck in `WAITING_CI` | required check name differs, or the workflow doesn't exist on the PR | check run must be named `helm-validate` (or set `REQUIRED_CHECKS`); after `CI_WAIT_TIMEOUT_SECONDS` the task moves to NEEDS_REVIEW |
| `WAITING_CI` with "waiting for Analyze Now" | Auto Analyze is off | click **Analyze Now** or enable Auto Analyze |
| Analysis FAILED, agent log shows auth error | Claude Code not logged in for the user running the backend | `claude` → `/login`; in Docker set `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` |
| Analysis FAILED "schema validation" | model returned malformed structured output twice | **Retry**; consider `CLAUDE_MODEL=opus` |
| Agent run "timeout" | slow model / large repo | raise `ANALYSIS_TIMEOUT_SECONDS` / `REMEDIATION_TIMEOUT_SECONDS` |
| Agent run stops at budget | `AGENT_MAX_BUDGET_USD` too low | raise it |
| NEEDS_REVIEW "scope violation" | the agent changed a file outside `REMEDIATION_ALLOWED_PATHS` (the fix is discarded) | review the Diff tab; adjust the allowlist only if the path is legitimately in scope |
| NEEDS_REVIEW "git push failed" | no push credentials, or the branch moved | `git ls-remote origin`; SSH agent loaded? `GIT_REMOTE_TEMPLATE` for HTTPS |
| NEEDS_REVIEW "PR head moved … fix discarded" | the developer pushed while remediation ran | expected behaviour: the task re-targets the new head automatically |
| Slack status "skipped" | `SLACK_WEBHOOK_URL` not set | set it in `.env`, restart |
| Slack status "failed HTTP 404 no_service" | webhook revoked | create a new Incoming Webhook |
| kubeconform `TOOL_ERROR` locally | no network to download schemas | run once online; schemas are cached in `var/kubeconform-cache` |
| Dashboard blank on :8000 | UI not built | `make build-ui` (or use `make dev-ui` on :5173) |
| "database is locked" | two API processes on the same `DATA_DIR` | run one API; use `RUN_WORKER=false` + `make worker` to split |

## Where to look

* **Dashboard → task → Timeline**: every state change, CI snapshot, agent start/finish, push and notification.
* **Agent logs tab**: each tool call the agent made, permission denials, cost, turns.
* `var/runs/task-<id>/analysis-<run>/`: the exact evidence bundle the agent saw (context.json, ci-log.txt, pr.diff).
* `var/rcp.db`: `sqlite3 var/rcp.db 'select id,state,resolution,last_error from tasks'`.
* API logs from `make dev` (structured `rcp.*` loggers).
