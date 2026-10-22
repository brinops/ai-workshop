"""Registration, state machine, CI aggregation, analysis/remediation contracts, redaction."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agents import analysis, remediation
from app.db import session_scope
from app.integrations.git_worktree import ChangedFile, is_protected
from app.integrations.github import CheckRun
from app.models import Event, Task, TaskState
from app.orchestration import ci
from app.orchestration.state_machine import InvalidTransition, can_transition, transition
from app.services.redaction import redact
from app.services.registration import register_pr
from tests.conftest import ANALYSIS_OK, FINDING, SHA1, pr_info

# ---------------------------------------------------------------- registration


def test_registration_is_idempotent():
    with session_scope() as db:
        first = register_pr(db, pr_info(), "hook")
        second = register_pr(db, pr_info(), "webhook")
        assert first.created and not second.created
        assert first.task.id == second.task.id
        assert db.query(Task).count() == 1
        assert first.task.state == TaskState.WAITING_CI
        types = [e.type for e in db.query(Event).filter(Event.task_id == first.task.id)]
        assert "registered" in types and "registration_duplicate" in types


def test_registration_distinct_prs():
    with session_scope() as db:
        a = register_pr(db, pr_info(number=1), "hook")
        b = register_pr(db, pr_info(number=2), "hook")
        assert a.task.id != b.task.id


def test_registration_ignores_own_remediation_commit():
    from app.models import Remediation

    with session_scope() as db:
        t = register_pr(db, pr_info(), "hook").task
        db.add(Remediation(task_id=t.id, attempt=1, base_sha=SHA1, commit_sha="c" * 40, push_status="pushed"))
        db.flush()
        res = register_pr(db, pr_info(sha="c" * 40), "webhook")
        assert not res.retargeted and t.expected_sha == SHA1


# ---------------------------------------------------------------- state machine


@pytest.mark.parametrize("src,dst,ok", [
    ("NEW", "WAITING_CI", True),
    ("WAITING_CI", "ANALYZING", True),
    ("ANALYZING", "TODO", True),
    ("TODO", "IN_PROGRESS", True),
    ("IN_PROGRESS", "VALIDATING", True),
    ("VALIDATING", "DONE", True),
    ("VALIDATING", "ANALYZING", True),
    ("NEW", "DONE", False),
    ("WAITING_CI", "IN_PROGRESS", False),
    ("DONE", "IN_PROGRESS", False),
    ("FAILED", "DONE", False),
    ("TODO", "VALIDATING", False),
])
def test_transition_table(src, dst, ok):
    assert can_transition(src, dst) is ok


def test_invalid_transition_raises_and_valid_records_event():
    with session_scope() as db:
        t = register_pr(db, pr_info(), "hook").task
        with pytest.raises(InvalidTransition):
            transition(db, t, TaskState.DONE.__class__("IN_PROGRESS"), "nope")
        transition(db, t, TaskState.ANALYZING, "ci failed")
        assert t.state == TaskState.ANALYZING
        last = db.query(Event).filter(Event.type == "state_changed").order_by(Event.id.desc()).first()
        assert last.data["from"] == "WAITING_CI" and last.data["to"] == "ANALYZING"


# ---------------------------------------------------------------- CI aggregation


def run(i, name, status, conclusion):
    return CheckRun(i, name, status, conclusion, None, None, None, None, "github-actions")


@pytest.mark.parametrize("runs,expected", [
    ([], "pending"),
    ([run(1, "helm-validate", "queued", None)], "pending"),
    ([run(1, "helm-validate", "completed", "success")], "success"),
    ([run(1, "helm-validate", "completed", "failure")], "failure"),
    ([run(1, "helm-validate", "completed", "timed_out")], "failure"),
    ([run(1, "helm-validate", "completed", "cancelled")], "cancelled"),
    ([run(1, "helm-validate", "completed", "skipped")], "skipped"),
    ([run(1, "helm-validate", "completed", "failure"), run(2, "helm-validate", "completed", "success")], "success"),
    ([run(1, "other", "completed", "failure")], "pending"),  # unrelated check never decides
])
def test_ci_aggregate(runs, expected):
    assert ci.aggregate(runs, ["helm-validate"]).overall == expected


def test_ci_aggregate_all_checks_when_none_required():
    res = ci.aggregate([run(1, "a", "completed", "success"), run(2, "b", "in_progress", None)], [])
    assert res.overall == "pending" and len(res.required) == 2


def test_extract_findings_from_actions_log():
    import json

    log = ("2024-05-01T10:00:00.1234567Z ##[group]Run validate\n"
           f"2024-05-01T10:00:01.0000000Z RCP-FINDING {json.dumps(FINDING)}\n"
           "2024-05-01T10:00:01.0000000Z RCP-FINDING {not json}\n")
    findings = ci.extract_findings(log)
    assert findings == [FINDING]
    assert "RCP-FINDING" in ci.log_excerpt(log)
    assert not ci.log_excerpt(log).startswith("2024")


# ---------------------------------------------------------------- analysis contract


def test_analysis_output_schema_rejects_bad_payloads():
    analysis.AnalysisOutput.model_validate(ANALYSIS_OK)
    with pytest.raises(ValidationError):
        analysis.AnalysisOutput.model_validate({**ANALYSIS_OK, "classification": "TYPO"})
    with pytest.raises(ValidationError):
        analysis.AnalysisOutput.model_validate({**ANALYSIS_OK, "confidence": 1.4})
    with pytest.raises(ValidationError):
        analysis.AnalysisOutput.model_validate({k: v for k, v in ANALYSIS_OK.items() if k != "root_cause"})
    schema = analysis.output_json_schema()
    assert schema["additionalProperties"] is False and "classification" in schema["required"]


def test_reconcile_deterministic_evidence_overrides_llm():
    out = analysis.AnalysisOutput.model_validate({**ANALYSIS_OK, "classification": "SCHEMA_VIOLATION"})
    rec = analysis.reconcile(out, [FINDING])
    assert rec.classification == "LOGICAL_CONFIGURATION_ERROR"
    assert rec.llm_classification == "SCHEMA_VIOLATION" and rec.agreement is False


def test_reconcile_priority_syntax_wins():
    findings = [{**FINDING, "category": "SCHEMA_VIOLATION"}, {**FINDING, "category": "SYNTAX_ERROR"}]
    assert analysis.deterministic_category(findings) == "SYNTAX_ERROR"
    assert analysis.deterministic_category([{**FINDING, "category": "TOOL_ERROR"}]) is None


@pytest.mark.parametrize("patch,reason", [
    ({"confidence": 0.3}, "confidence"),
    ({"auto_remediation_appropriate": False}, "human review"),
    ({"classification": "NON_REMEDIABLE"}, "outside the automatic remediation scope"),
    ({"proposed_fix": {"summary": "x", "steps": [], "changes": [{"file": "app/main.py", "description": "x"}]}},
     "non-allowlisted"),
])
def test_reconcile_blocks_unsafe_auto_fix(patch, reason):
    out = analysis.AnalysisOutput.model_validate({**ANALYSIS_OK, **patch})
    rec = analysis.reconcile(out, [] if patch.get("classification") else [FINDING])
    assert rec.remediable is False and reason in rec.decision_reason


def test_render_markdown_mentions_override():
    out = analysis.AnalysisOutput.model_validate({**ANALYSIS_OK, "classification": "SYNTAX_ERROR"})
    md = analysis.render_markdown(out, analysis.reconcile(out, [FINDING]), [FINDING])
    assert "overridden" in md and "| LOGICAL_CONFIGURATION_ERROR |" in md


# ---------------------------------------------------------------- remediation permissions & scope


def test_tool_permissions_are_least_privilege(tmp_path):
    tools, allowed = remediation.tool_permissions(tmp_path)
    assert "WebFetch" not in tools and "Write" not in tools
    edit_rules = [a for a in allowed if a.startswith("Edit(")]
    assert edit_rules == [f"Edit(/{tmp_path.resolve()}/demo/charts/**)"]
    bash_rules = [a for a in allowed if a.startswith("Bash(")]
    assert len(bash_rules) == 1 and "validate.py" in bash_rules[0]
    assert "Bash" not in allowed and "Edit" not in allowed  # never unrestricted


def test_scope_check():
    ok = remediation.check_scope([ChangedFile("demo/charts/payments-api/values.yaml", "M", 1, 1)])
    assert ok.ok
    bad = remediation.check_scope([ChangedFile(".github/workflows/helm-validate.yaml", "M", 1, 1)])
    assert not bad.ok and "outside allowlist" in bad.violations[0]
    deleted = remediation.check_scope([ChangedFile("demo/charts/payments-api/templates/service.yaml", "D", 0, 20)])
    assert not deleted.ok
    huge = remediation.check_scope([ChangedFile("demo/charts/payments-api/values.yaml", "M", 100, 100)])
    assert not huge.ok
    assert not remediation.check_scope([]).ok


def test_protected_branches():
    assert is_protected("main") and is_protected("release/1.2")
    assert not is_protected("demo/logical-error-20250101")


def test_build_command_never_bypasses_permissions(tmp_path):
    from app.integrations.claude_runner import AgentSpec, build_command

    tools, allowed = remediation.tool_permissions(tmp_path)
    cmd = build_command(AgentSpec(prompt="x", tools=tools, allowed_tools=allowed, json_schema={}, agent="k8s-remediator"))
    assert "--dangerously-skip-permissions" not in cmd
    assert cmd[cmd.index("--permission-mode") + 1] == "dontAsk"
    assert "--max-budget-usd" in cmd and "--json-schema" in cmd


def test_agent_env_drops_credentials(monkeypatch):
    from app.integrations.claude_runner import agent_env

    monkeypatch.setenv("GITHUB_TOKEN", "ghp_secret")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/x")
    env = agent_env()
    assert "GITHUB_TOKEN" not in env and "SLACK_WEBHOOK_URL" not in env and env["RCP_AGENT"] == "1"


# ---------------------------------------------------------------- redaction


def test_redaction():
    text = ("token ghp_abcdefghijklmnopqrstuvwxyz0123 and https://hooks.slack.com/services/T0/B0/xyz "
            "Authorization: Bearer abc.def.ghi password=hunter22")
    out = redact(text)
    assert "ghp_" not in out and "hooks.slack.com/services/T0" not in out
    assert "abc.def.ghi" not in out and "hunter22" not in out


# ---------------------------------------------------------------- agent log detail


def test_parse_event_keeps_full_tool_input_and_output():
    from app.integrations.claude_runner import parse_event

    lines: list[tuple] = []

    def emit(kind, text, detail=None):
        lines.append((kind, text, detail))

    long_output = "\n".join(f"line {i}" for i in range(300))
    parse_event({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Edit", "input": {"file_path": "/wt/values.yaml", "old_string": "9090", "new_string": "8080"}},
    ]}}, emit, {})
    parse_event({"type": "user", "message": {"content": [
        {"type": "tool_result", "content": long_output, "is_error": False},
    ]}}, emit, {})
    parse_event({"type": "result", "subtype": "success", "num_turns": 3, "total_cost_usd": 0.01,
                 "structured_output": {"status": "fixed"}}, emit, {})

    (k1, t1, d1), (k2, t2, d2), (k3, _, d3) = lines
    assert k1 == "tool_use" and t1 == "Edit · /wt/values.yaml" and '"new_string": "8080"' in d1
    assert k2 == "tool_result" and len(t2) < 410 and d2 == long_output  # summary truncated, detail complete
    assert k3 == "result" and '"status": "fixed"' in d3
