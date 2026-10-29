# A real run, file by file

[`pr-16-scenario-c/`](pr-16-scenario-c/) is everything the control plane produced for one real pull request —
[brinops/ai-workshop#16](https://github.com/brinops/ai-workshop/pull/16), demo scenario C — exported unchanged
from the database, the run bundle and the API. Use it to show *what actually flows between the pieces*
described in [HOW_IT_WORKS.md](../HOW_IT_WORKS.md).

**The PR:** "Expose payments-api metrics port on the Service" changes `service.targetPort: 8080 → 9090`.
YAML, `helm lint`, `helm template` and kubeconform all pass; only the consistency check catches that nothing
listens on 9090.

**The outcome:** diagnosed as `LOGICAL_CONFIGURATION_ERROR` (93%), fixed with a one-line commit
(`6c28a12`), CI green, Slack notified. **3 min 55 s** from `gh pr create` to `DONE`, **$0.345** in agent cost.

The run used manual approvals (Auto Analyze / Remediate / Push off), so the timeline also shows the three
dashboard clicks — **Analyze Now**, **Start Remediation**, **Approve Push**. With automation on, the same
artifacts are produced without the waits.

## Timeline

From [`06-api/events-timeline.json`](pr-16-scenario-c/06-api/events-timeline.json) (UTC):

| Time | Stage | What happened |
|---|---|---|
| 06:44:38 | Registration | Hook registers PR #16 → task 14, `NEW → WAITING_CI` |
| 06:45:00 | CI | `helm-validate` failed on `83d7e6e`; route `helm-validate` selected |
| 06:45:04 | Analysis | **Analyze Now** clicked → `ANALYZING`, analysis agent started |
| 06:45:16 | Analysis | Local validator reproduces the CI finding |
| 06:45:37 | Analysis | Diagnosis `LOGICAL_CONFIGURATION_ERROR` (93%), 14 turns, $0.312 → `TODO` |
| 06:46:13 | Remediation | **Start Remediation** clicked → `IN_PROGRESS`, attempt 1/2 |
| 06:47:01 | Remediation | Agent done (5 turns, $0.033); scope + validator OK; committed `6c28a12` |
| 06:48:11 | Push | **Approve Push** clicked |
| 06:48:16 | Push | Fast-forward push to the PR branch → `VALIDATING` |
| 06:48:33 | Verification | `helm-validate` green on `6c28a12` → `DONE` (`remediated`) |
| 06:48:34 | Notification | Slack message sent |

## Folder map

| File | Produced by | What it is |
|---|---|---|
| **01-registration/** | | |
| `hook-request.json` | `.claude/hooks/register_pr.py` | Body of `POST /api/tasks/register` after `gh pr create` |
| **02-ci/** | | |
| `ci-snapshots.json` | worker (GitHub check runs) | Every observed CI state change: pending → failure on the PR commit, success on the fix |
| **03-analysis/** | | |
| `bundle/context.json` | worker | PR metadata, changed files, selected route, deterministic findings — the agent's main input |
| `bundle/ci-log.txt` | worker (GitHub job log) | The failed job log, including the validator's `RCP-FINDING {json}` lines |
| `bundle/pr.diff` | worker (GitHub) | The PR diff |
| `bundle/local-validation.json` | validator on the PR head | Same validator CI runs, re-run locally — evidence the agent can trust |
| `validation-pre-analysis.json` | worker | That validator run as stored in `validation_runs` |
| `agent-run.json` | worker | `agent_runs` row: model, turns, cost, timing |
| `agent-transcript.jsonl` | Claude Code `stream-json` | Every message, tool call and tool result of the analysis agent (what the dashboard log shows) |
| `agent-output.json` | **Analysis Skill** | The diagnosis, validated against the JSON schema |
| `diagnosis-comment.md` | worker | The diagnosis as rendered on the dashboard, incl. the reconciliation verdict |
| **04-remediation/** | | |
| `agent-run.json`, `agent-transcript.jsonl` | worker / Claude Code | Same as above, for the remediation agent |
| `agent-output.json` | **Remediation Subagent** | What the agent *claims* it did |
| `fix.diff` | worker (`git diff`) | What it *actually* did — computed by the worker, not reported by the agent |
| `validation-post-remediation.json` | worker | Validator re-run on the fixed worktree |
| `remediation-record.json` | worker | `remediations` row: scope check, validation, commit, push status |
| `remediation-comment.md` | worker | The remediation report on the dashboard |
| **05-notification/** | | |
| `slack-remediated.json` | worker | The exact Slack Block Kit payload that was sent (rebuilt with the same code) |
| `notification-remediated.json` | worker | `notifications` row: sent / failed / skipped |
| **06-api/** | | |
| `task-detail.json` | API `GET /api/tasks/14` | Everything the task page in the dashboard renders |
| `events-timeline.json` | API | The audit log / timeline, trimmed to `ts, type, level, message` |

## Walkthrough

### 1. Registration — the hook

[`hook-request.json`](pr-16-scenario-c/01-registration/hook-request.json) is all the developer side sends:
repo, PR number, URL, branch and head SHA. The backend does not trust it — it re-reads the PR from GitHub
before creating the task.

### 2. CI — the worker polls, no agent yet

[`ci-snapshots.json`](pr-16-scenario-c/02-ci/ci-snapshots.json) has three snapshots: `pending` and `failure`
on `83d7e6e` (the PR), then `success` on `6c28a12` (the fix). The check name `helm-validate` is what selects
the route in `control-plane.yaml` — not the model.

### 3. Analysis — evidence in, diagnosis out

**Input.** The worker collects the [bundle](pr-16-scenario-c/03-analysis/bundle/) *before* any model runs.
The key line in [`ci-log.txt`](pr-16-scenario-c/03-analysis/bundle/ci-log.txt) is the validator's machine-readable
finding:

```text
RCP-FINDING {"category": "LOGICAL_CONFIGURATION_ERROR", "check": "service-target-port", ...}
```

That category is *deterministic*: it comes from code, and it wins if the model disagrees.

**Output.** [`agent-output.json`](pr-16-scenario-c/03-analysis/agent-output.json) — the schema-validated
diagnosis:

```json
{
  "classification": "LOGICAL_CONFIGURATION_ERROR",
  "root_cause": "In demo/charts/payments-api/values.yaml, the PR changed `service.targetPort` from 8080 to 9090, ...",
  "affected_files": [{ "path": "demo/charts/payments-api/values.yaml", "line": 20, "reason": "..." }],
  "evidence": [{ "source": "validator", "detail": "..." }, { "source": "ci_log", "detail": "..." }, ...],
  "proposed_fix": { "summary": "Restore `service.targetPort` to 8080 ...", "changes": [ ... ] },
  "confidence": 0.93,
  "auto_remediation_appropriate": true,
  "auto_remediation_rationale": "..."
}
```

Worth pointing out on stage:

- every claim cites its `source` — validator, CI log, diff, file, PR metadata;
- the agent noticed the PR **title** ("expose metrics port") doesn't match the **diff**, and says so rather
  than inventing a metrics port;
- [`diagnosis-comment.md`](pr-16-scenario-c/03-analysis/diagnosis-comment.md) shows the reconciliation line:
  *"Deterministic evidence: `LOGICAL_CONFIGURATION_ERROR` — the model agrees."*

[`agent-transcript.jsonl`](pr-16-scenario-c/03-analysis/agent-transcript.jsonl) shows how it got there: load the
skill, read the four bundle files, read `values.yaml`, `service.yaml`, `deployment.yaml`, return the result.
Read-only tools only (`Read`, `Grep`, `Glob`, plus `Skill` to load its instructions).

### 4. Remediation — the agent edits, the worker verifies

[`agent-output.json`](pr-16-scenario-c/04-remediation/agent-output.json) is the agent's report
(`"status": "fixed"`, `service.targetPort 9090 → 8080`, validator passed). The worker does not take its word for it:

- [`fix.diff`](pr-16-scenario-c/04-remediation/fix.diff) is computed by the worker from the worktree;
- [`remediation-record.json`](pr-16-scenario-c/04-remediation/remediation-record.json) records the worker's own
  checks — `scope_ok` (only `demo/charts/**`, ≤ 40 lines), `validation_passed`, then `commit_sha` and
  `push_status: pushed`.

```diff
   # Must route to the container port the application listens on.
-  targetPort: 9090
+  targetPort: 8080
```

The [transcript](pr-16-scenario-c/04-remediation/agent-transcript.jsonl) is five steps: read `values.yaml`,
edit it, run the validator (the only Bash command it is allowed), return the result. No git, no network —
the worker commits and pushes.

### 5. Notification

[`slack-remediated.json`](pr-16-scenario-c/05-notification/slack-remediated.json) is the Block Kit message:
headline, repo / PR / classification / validation fields, original problem, root cause, files changed, diff,
and links to the PR, the commit and the dashboard. Payloads pass through secret redaction before sending.

### 6. What the dashboard reads

[`task-detail.json`](pr-16-scenario-c/06-api/task-detail.json) is the single API response behind the task
page: `task`, `events`, `comments`, `runs`, `remediations`, `validations`, `ci`, `notifications`. The dashboard
only renders these rows; its buttons only flip fields that the worker picks up on its next tick.

## Notes on the data

- The local checkout path is replaced with `<control-plane>`; nothing else is edited.
- `ci-log.txt` is the raw GitHub Actions log, ANSI colour codes included; GitHub itself masks the token as `***`.
- Database booleans appear as `0` / `1`.

## Regenerating

After any finished run (the API must be up):

```bash
just export-run <task-id> docs/examples/<name>
```

[`scripts/export_run.py`](../../scripts/export_run.py) reads the database, the run bundle and
`GET /api/tasks/<id>`, rebuilds the Slack payload with the worker's own code, and anonymises local paths.
