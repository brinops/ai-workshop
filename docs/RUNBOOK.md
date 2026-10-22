# Workshop Runbook

Goal: show one PR going from a broken Helm configuration to a green, remediated PR — live, end to end.
Scenario C (logical error) is the strongest story: the YAML is valid, the schema is valid, and only a
deterministic consistency check plus contextual reasoning find and fix the bug.

## T–1 day

1. `just install && just build-ui`
2. `cp .env.example .env`, set `SLACK_WEBHOOK_URL` (and `PUBLIC_URL` if the dashboard is reachable elsewhere).
3. Make sure `main` contains the chart, validator and `.github/workflows/helm-validate.yaml`
   (`just preflight` checks this).
4. Rehearse the agents without GitHub: `just dry-run C` (≈2 min, ≈$0.40). Expect
   `classification=LOGICAL_CONFIGURATION_ERROR … remediable=True` and `local validation after fix: VALID`.
5. Run one full rehearsal of the flow below and delete the rehearsal PR afterwards
   (`gh pr close <n> --delete-branch`).

## T–15 minutes

```bash
just dev                         # terminal 1 — API + worker + dashboard on :8000
just preflight                   # terminal 2 — every required check must be ✓
python3 scripts/preflight.py --live --slack   # optional: real Claude call + Slack test message
```

Open http://localhost:8000, switch on **Presentation mode**, and choose the automation preset:

* **Autonomous demo** (all three toggles on) — the PR fixes itself; best for time-boxed talks.
* **Safe** (Auto Push off) — pause at "Approve Push" to show the human-in-the-loop gate.

## Live demo (≈6–8 minutes)

| # | You do | Audience sees |
|---|---|---|
| 1 | In terminal 2: `just scenario C` | branch `demo/logical-error-<ts>` pushed; validator output proves it fails for the intended reason |
| 2 | Start Claude Code in the repo (`claude`) and ask: *"Open a PR for branch demo/logical-error-… using the gh command printed above."* Claude runs `gh pr create …` | Claude Code prints `[Remediation Control Plane] PR #N registered as task K` (PostToolUse hook) |
| 3 | Switch to the dashboard | task card appears in **NEW** → `WAITING_CI`, "Waiting for GitHub Actions: helm-validate" |
| 4 | Open the PR on GitHub (link on the card) | the real `helm-validate` check runs and fails (~40 s) with an annotation on `service.yaml` |
| 5 | Dashboard | `ANALYZING` — the agent log streams tool calls (Skill → Read context.json → ci-log → diff → values.yaml → templates) |
| 6 | Open the task → **Diagnosis** | `LOGICAL_CONFIGURATION_ERROR`, root cause "targetPort 9090 ≠ app.port 8080", deterministic evidence agrees, proposed fix |
| 7 | Dashboard | **TODO** → **IN PROGRESS**: Remediation Subagent edits `values.yaml`, runs the validator |
| 8 | **Diff** tab | one-line diff `targetPort: 9090 → 8080`; scope check passed; local validation passed |
| 9 | (Safe mode) click **Approve Push** | commit pushed to the same PR branch → `VALIDATING` |
| 10 | GitHub PR | new commit by "RCP Remediation Agent", `helm-validate` re-runs and passes |
| 11 | Dashboard | task → **DONE** (`remediated`), timeline shows the full history |
| 12 | Slack channel | message with repo/PR, problem, classification, root cause, files, diff, validation, links |

Talking points while waiting for CI: the validator is the same code in CI, in the backend and in the agent's
toolbox; the agent cannot push, run git or edit outside `demo/charts/**`; the LLM's classification is
overridden whenever deterministic evidence disagrees.

## Variations

* **Scenario A** (`just scenario A`) — syntax error: shows deterministic YAML parse evidence.
* **Scenario B** (`just scenario B`) — schema violation: kubeconform output in the CI log.
* **Manual gates** — turn off Auto Analyze to show *Analyze Now*; turn off Auto Remediate for *Start Remediation*.
* **Pause / Cancel** — pause a task in `ANALYZING`: the running agent finishes, nothing further starts until *Resume*.
  *Cancel* stops the running agent process immediately.
* **Crash recovery** — stop `just dev` (Ctrl-C) during `IN_PROGRESS`, start it again: the task is recovered and the
  stage re-runs from a fresh worktree (timeline shows "Recovered …").

## Reset between sessions

```bash
just reset-prs       # close demo PRs and delete their branches
just reset-db        # optional: clears the dashboard history
```

## If something goes wrong on stage

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md). Fast fallbacks:

* Hook didn't fire → `python3 .claude/hooks/register_pr.py --register <PR URL>`.
* CI slow → talk through the Diagnosis of a previous task; the worker keeps polling.
* Agent failed → open **Agent logs** to show why (this is a feature: the failure is explained, nothing is faked),
  then **Retry**.
