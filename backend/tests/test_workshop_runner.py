import asyncio
import json
import sys

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.agents.workshop import StageInput
from app.api.workshop_runs import change_handoff_state
from app.config import REPO_ROOT, get_settings
from app.control_plane import get_config
from app.db import session_scope
from app.integrations.claude_runner import AgentResult
from app.integrations.training_jira import TrainingJira
from app.models.jira_workflow import JiraWorkflowEvent, JiraWorkflowOperation, JiraWorkflowProfile, JiraWorkflowRun
from app.orchestration.booking_repair import KIND, claim_repair, execute_repair
from app.orchestration.worker import Worker

RUN_ID = "run-workshop"


@pytest.fixture
def issue():
    with session_scope() as db:
        issue = TrainingJira(db).create_booking_issue("reporter-workshop")
        db.add(JiraWorkflowProfile(
            profile_id="profile-workshop", local_instance_id="local-workshop", source_kind=issue.source.kind,
            source_instance_id=issue.source.instance_id, source_reporter_id=issue.reporter_id,
            slack_workspace_id="TWORK", slack_user_id="UWORK",
        ))
        db.flush()
        db.add(JiraWorkflowRun(
            run_id=RUN_ID, profile_id="profile-workshop", source_kind=issue.source.kind,
            source_instance_id=issue.source.instance_id, issue_id=issue.issue_id, issue_key=issue.issue_key,
            source_reporter_id=issue.reporter_id, slack_user_id="UWORK",
        ))
    return issue


def _claude(tmp_path, monkeypatch, code, *, timeout=5):
    executable = tmp_path / "mock-claude"
    executable.write_text(f"#!{sys.executable}\n{code}")
    executable.chmod(0o700)
    monkeypatch.setenv("CLAUDE_BIN", str(executable))
    monkeypatch.setenv("JIRA_WORKSHOP_AGENT_TIMEOUT_SECONDS", str(timeout))
    get_settings.cache_clear()


def _finished(attempt_id):
    with session_scope() as db:
        return db.scalar(select(JiraWorkflowEvent).where(
            JiraWorkflowEvent.event_id == f"{attempt_id}:finished",
        )).payload


async def test_worker_uses_workshop_profile_and_validates_structured_result(tmp_path, monkeypatch, issue):
    _claude(tmp_path, monkeypatch, """
import json
import subprocess
import sys
from pathlib import Path
args = sys.argv[1:]
assert args[args.index('--agent') + 1] == 'workshop-triage'
assert 'Ukrainian' in args[args.index('--append-system-prompt') + 1]
assert 'Read(./demo/booking/service.py)' in args and 'Read' not in args
assert Path('.claude/agents/workshop-investigation.md').is_file()
assert Path('.claude/skills/workshop-tone-of-voice/SKILL.md').is_file()
assert not Path('.claude/agents/k8s-remediator.md').exists()
assert not Path('.claude/skills/k8s-failure-analysis').exists()
assert not Path('.claude/hooks/register_pr.py').exists()
settings = json.loads(Path('.claude/settings.json').read_text())
assert set(settings['hooks']) == {'SubagentStart', 'SubagentStop'}
assert settings['env']['CLAUDE_CODE_DISABLE_BACKGROUND_TASKS'] == '1'
assert Path('demo/booking/service.py').is_file()
assert not Path('demo/booking/scenario.json').exists()
request = json.load(sys.stdin)
assert request['run_id'] == 'run-workshop'
assert request['stage'] == 'triage'
for role in ('workshop-investigation', 'workshop-communication'):
    print(json.dumps({'type':'assistant','message':{'content':[
        {'type':'tool_use','name':'Agent','input':{'subagent_type':role,'prompt':'private prompt'}}
    ]}}))
for agent_id, kind in (('agent-1', 'SubagentStart'), ('agent-1', 'SubagentStart'),
                       ('agent-1', 'SubagentStop'), ('agent-2', 'SubagentStart')):
    subprocess.run([sys.executable, '.claude/hooks/record_subagent.py'], check=True,
                   input=json.dumps({'hook_event_name': kind, 'agent_id': agent_id,
                                     'agent_type': 'workshop-investigation',
                                     'last_assistant_message': 'private report'}), text=True)
print(json.dumps({'type':'result','structured_output':{
    'schema_version':1,'kind':'ask_questions','questions':['Скільки місць було?'],
    'slack_text':'Скільки місць було?'
}}))
""")
    attempt = await Worker().run_workshop_stage(RUN_ID, StageInput(stage="triage", issue=issue), asyncio.Event())
    assert attempt.status == "succeeded" and attempt.output.kind == "ask_questions"
    result = _finished(attempt.attempt_id)
    assert result["delegated_agents"] == ["workshop-investigation", "workshop-communication"]
    assert result["output_kind"] == "ask_questions" and "private prompt" not in str(result)
    assert result["hook_status"] == "recorded"
    with session_scope() as db:
        lifecycle = db.scalars(select(JiraWorkflowEvent).where(
            JiraWorkflowEvent.event_type.in_(("workshop.subagent_started", "workshop.subagent_finished")),
        ).order_by(JiraWorkflowEvent.id)).all()
    assert [(event.payload["agent_id"], event.event_type) for event in lifecycle] == [
        ("agent-1", "workshop.subagent_started"), ("agent-1", "workshop.subagent_finished"),
        ("agent-2", "workshop.subagent_started"),
    ]
    assert all(event.payload["attempt_id"] == attempt.attempt_id for event in lifecycle)
    assert all("private report" not in str(event.payload) for event in lifecycle)



@pytest.mark.parametrize(("code", "timeout", "expected_status", "expected_error"), [
    ("import time; time.sleep(10)", 0.1, "timeout", "agent timeout"),
    ("import sys; print('provider rejected the request', file=sys.stderr); sys.exit(2)", 5, "failed", "provider rejected"),
    ("""import json
print(json.dumps({'type':'result','structured_output':{
    'schema_version':1, 'kind':'ask_questions', 'slack_text':'Текст', 'questions':[]
}}))
""", 5, "failed", "invalid structured output"),
])
async def test_worker_preserves_retry_diagnostics(tmp_path, monkeypatch, issue, code, timeout, expected_status, expected_error):
    _claude(tmp_path, monkeypatch, code, timeout=timeout)
    attempt = await Worker().run_workshop_stage(RUN_ID, StageInput(stage="triage", issue=issue), asyncio.Event())
    assert attempt.status == expected_status and attempt.output is None
    diagnostic = _finished(attempt.attempt_id)
    assert diagnostic["status"] == expected_status and diagnostic["retryable"]
    assert diagnostic["hook_status"] == "no_hook_events"
    assert expected_error in diagnostic["error"]
    with session_scope() as db:
        assert db.get(JiraWorkflowRun, RUN_ID).state == "discovered"
        assert db.scalar(select(JiraWorkflowEvent).where(
            JiraWorkflowEvent.event_id == f"{attempt.attempt_id}:started",
        )) is not None


async def test_worker_records_launch_error_and_can_retry(tmp_path, monkeypatch, issue):
    request = StageInput(stage="triage", issue=issue)
    monkeypatch.setenv("CLAUDE_BIN", str(tmp_path / "missing-claude"))
    get_settings.cache_clear()
    worker = Worker()
    first = await worker.run_workshop_stage(RUN_ID, request, asyncio.Event())
    assert first.status == "failed" and _finished(first.attempt_id)["retryable"]
    _claude(tmp_path, monkeypatch, """import json
print(json.dumps({'type':'result','structured_output':{
    'schema_version':1,'kind':'ask_questions','slack_text':'Уточни, будь ласка.','questions':['Де?']
}}))
""")
    second = await worker.run_workshop_stage(RUN_ID, request, asyncio.Event())
    assert second.status == "succeeded" and second.attempt_id != first.attempt_id
    assert _finished(first.attempt_id)["status"] == "failed"


async def test_reply_schema_requires_object_and_limits_additional_questions(tmp_path, monkeypatch, issue):
    _claude(tmp_path, monkeypatch, """
import json
import sys
schema = json.loads(sys.argv[sys.argv.index('--json-schema') + 1])
assert schema['type'] == 'object' and 'anyOf' not in schema
assert 'propose_description_append' in schema['properties']['kind']['enum']
print(json.dumps({'type':'result','structured_output':{
    'schema_version':1,'kind':'ask_questions','slack_text':'Уточни, будь ласка.','questions':['Де?', 'Коли?']
}}))
""")
    attempt = await Worker().run_workshop_stage(RUN_ID, StageInput(stage="reply", issue=issue), asyncio.Event())
    assert attempt.status == "failed"
    assert "too_long" in _finished(attempt.attempt_id)["error"]


async def test_booking_plan_is_persisted_before_repair_and_reused(issue, monkeypatch):
    monkeypatch.setenv("CONTROL_PLANE_CONFIG", str(REPO_ROOT / "control-plane.yaml"))
    get_settings.cache_clear()
    get_config.cache_clear()
    op_id = f"{RUN_ID}:booking-repair"
    with session_scope() as db:
        db.get(JiraWorkflowRun, RUN_ID).state = "ready_for_handoff"
        db.add(JiraWorkflowOperation(
            operation_id=op_id, run_id=RUN_ID, kind=KIND, status="pending",
            payload={"approved_report": "Report"},
        ))
    plan = {"goal": "Avoid double booking", "steps": ["Recheck capacity"], "acceptance_criteria": ["One confirmation"]}
    routed_plan = {**plan, "route": {
        "id": "booking-backend", "execution_agent": "workshop-booking-backend", "qa_agent": "workshop-booking-qa",
    }}
    calls = []

    async def agent(spec, *_):
        calls.append(spec.agent)
        payload = json.loads(spec.prompt)
        if spec.agent == "workshop-planning":
            assert "plan" not in payload
            assert "booking-backend" in payload["routes"]
            return AgentResult(status="succeeded", structured={**plan, "route": "booking-backend"})
        assert payload["plan"] == routed_plan
        return AgentResult(status="failed", error="Execution failed")

    cancel = asyncio.Event()
    with pytest.raises(HTTPException, match="implementation plan must be ready"), session_scope() as db:
        change_handoff_state(RUN_ID, "start", db)
    claim = claim_repair(5)
    assert claim and claim[-1] is None
    await execute_repair(*claim, agent, cancel, 5)
    with session_scope() as db:
        op = db.get(JiraWorkflowOperation, op_id)
        assert op.status == "planned" and op.result["plan"] == routed_plan
    assert claim_repair(5) is None
    with session_scope() as db:
        assert change_handoff_state(RUN_ID, "start", db).state == "in_progress"
    claim = claim_repair(5)
    assert claim and claim[-1].model_dump() == routed_plan
    await execute_repair(*claim, agent, cancel, 5)
    with session_scope() as db:
        op = db.get(JiraWorkflowOperation, op_id)
        assert op.status == "failed" and op.result["plan"] == routed_plan
    assert calls == ["workshop-planning", "workshop-booking-backend"]
