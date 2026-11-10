import json

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.db import session_scope
from app.integrations.claude_runner import AgentResult
from app.integrations.training_jira import AppendDescription, TrainingJira
from app.models.jira_workflow import (
    JiraWorkflowDecision,
    JiraWorkflowDraft,
    JiraWorkflowEvent,
    JiraWorkflowOperation,
    JiraWorkflowProfile,
    JiraWorkflowRun,
)
from app.models.training_jira import TrainingIssueWrite
from app.orchestration import worker as worker_module
from app.orchestration.worker import Deps, Worker
from app.services.slack_inbox import store_draft_action, store_thread_reply

RUN = "run-dialog"
ROOT = "1794306000.000001"
TEAM = "TWORK"
CHANNEL = "CWORK"
USER = "UWORK"


@pytest.fixture
def training_run():
    with session_scope() as db:
        issue = TrainingJira(db).create_booking_issue("reporter-dialog")
        db.add(JiraWorkflowProfile(
            profile_id="profile-dialog", local_instance_id="local-dialog", source_kind="training",
            source_instance_id=issue.source.instance_id, source_reporter_id=issue.reporter_id,
            slack_workspace_id=TEAM, slack_user_id=USER,
        ))
        db.flush()
        db.add(JiraWorkflowRun(
            run_id=RUN, profile_id="profile-dialog", source_kind="training",
            source_instance_id=issue.source.instance_id, issue_id=issue.issue_id, issue_key=issue.issue_key,
            source_reporter_id=issue.reporter_id, slack_user_id=USER,
            slack_workspace_id=TEAM, slack_channel_id=CHANNEL, slack_thread_ts=ROOT,
        ))
    return issue


async def _publish_pending(_settings):
    with session_scope() as db:
        op = db.scalar(select(JiraWorkflowOperation).where(
            JiraWorkflowOperation.kind == "post_reply", JiraWorkflowOperation.status == "pending",
        ).order_by(JiraWorkflowOperation.created_at).limit(1))
        if op:
            published = db.scalars(select(JiraWorkflowOperation).where(
                JiraWorkflowOperation.kind == "post_reply", JiraWorkflowOperation.status == "opened",
            )).all()
            ts = f"1794306000.{(len(published) + 1) * 100:06d}"
            op.status, op.result = "opened", {"thread_ts": ts}
            if op.draft_id:
                db.get(JiraWorkflowDraft, op.draft_id).slack_message_ts = ts


def _reply(event_id, ts, text):
    return store_thread_reply({"type": "event_callback", "team_id": TEAM, "event_id": event_id, "event": {
        "type": "message", "channel": CHANNEL, "thread_ts": ROOT, "ts": ts, "user": USER, "text": text,
    }}, TEAM)


def _click(draft, ts, action="request_revision"):
    return store_draft_action({
        "type": "block_actions", "team": {"id": TEAM}, "user": {"id": USER},
        "container": {"type": "message", "channel_id": CHANNEL, "message_ts": draft.slack_message_ts},
        "actions": [{"action_id": action, "action_ts": ts,
                     "value": json.dumps({"draft_id": draft.draft_id, "draft_version": draft.version})}],
    }, TEAM)


def _output(kind, **fields):
    return AgentResult(status="succeeded", structured={"schema_version": 1, "kind": kind, "slack_text": "Тест.", **fields})


async def _tick(worker):
    await worker.tick()
    if worker._workshop_job:
        await worker._workshop_job


def _enable(monkeypatch):
    monkeypatch.setenv("JIRA_WORKSHOP_DIALOG_ENABLED", "true")
    monkeypatch.setenv("WORKSHOP_SLACK_APP_TOKEN", "xapp-test")
    get_settings.cache_clear()
    monkeypatch.setattr(worker_module, "deliver_next_thread", _publish_pending)


async def test_dialogue_follows_slack_events_and_publishes_new_draft(monkeypatch, training_run):
    _enable(monkeypatch)
    block = {"heading": "Уточнення", "steps": ["Забронювати останнє місце."], "actual": "Два підтвердження.",
             "expected": "Другий у листі очікування.", "evidence": [], "open_questions": []}
    calls = []

    async def agent(spec, *_):
        request = json.loads(spec.prompt)
        stage = request["stage"]
        calls.append(stage)
        if stage == "triage":
            return _output("ask_questions", questions=["Скільки місць залишалося?"])
        if stage == "reply" and not request["follow_up_rounds_used"]:
            return _output("ask_questions", questions=["Який результат очікувався?"])
        if stage == "reply":
            assert request["replies"][-1]["text"] == "Другий мав чекати."
            return _output("propose_description_append", block=block)
        if stage == "request_revision":
            return _output("request_revision")
        if stage == "result":
            assert request["write_result"]["outcome"] == "applied"
            return _output("report_result")
        assert stage == "revision" and request["previous_block"] == block
        assert any(reply["text"] == "Вкажи два різні акаунти." for reply in request["replies"])
        return _output("propose_description_append", block={**block, "steps": ["Одночасно з двох різних акаунтів."]})

    worker = Worker(Deps(run_agent=agent))
    await _tick(worker)  # triage
    await _tick(worker)  # publish questions
    assert _reply("EvFirst", "1794306000.000110", "Одне місце.")
    assert not _reply("EvFirst", "1794306000.000110", "Одне місце.")
    await _tick(worker)  # follow-up
    await _tick(worker)  # publish follow-up
    assert _reply("EvStale", "1794306000.000190", "До повторного питання.")
    assert _reply("EvSecond", "1794306000.000220", "Другий мав чекати.")
    await _tick(worker)  # draft 1
    await _tick(worker)  # publish draft 1
    with session_scope() as db:
        first = db.scalars(select(JiraWorkflowDraft)).one()
    assert _click(first, "1794306000.000310")
    assert not _click(first, "1794306000.000310")
    await _tick(worker)  # revision request
    # Feedback may arrive before the agent's request for revision is posted.
    assert _reply("EvRevision", "1794306000.000350", "Вкажи два різні акаунти.")
    await _tick(worker)  # publish request, prepare draft 2
    await _tick(worker)  # publish draft 2
    assert _click(first, "1794306000.000520")  # new click, old version
    await _tick(worker)
    with session_scope() as db:
        drafts = db.scalars(select(JiraWorkflowDraft).order_by(JiraWorkflowDraft.version)).all()
        run = db.get(JiraWorkflowRun, RUN)
        assert (run.state, run.follow_up_rounds_used) == ("waiting_for_approval", 1)
        assert [(draft.version, draft.status) for draft in drafts] == [(1, "revision_requested"), (2, "pending_approval")]
        assert "двох різних акаунтів" in drafts[1].rendered_append and drafts[1].slack_message_ts
        assert db.scalars(select(JiraWorkflowDecision)).one().decision == "request_revision"
        assert db.scalars(select(JiraWorkflowEvent).where(JiraWorkflowEvent.outcome == "stale_draft")).one()
        assert db.scalars(select(JiraWorkflowEvent).where(JiraWorkflowEvent.outcome == "stale_reply")).one()
        assert TrainingJira(db).get_issue(training_run.issue_id, training_run.reporter_id) == training_run
    assert calls == ["triage", "reply", "reply", "request_revision", "revision"]
    assert _click(drafts[0], "1794306000.000530", "approve")
    assert _click(drafts[1], "1794306000.000540", "approve")
    assert not _click(drafts[1], "1794306000.000540", "approve")
    assert _click(drafts[1], "1794306000.000550", "approve")
    await _tick(worker)
    await _tick(worker)
    with session_scope() as db:
        approvals = db.scalars(select(JiraWorkflowEvent).where(
            JiraWorkflowEvent.payload["action"].as_string() == "approve",
        ).order_by(JiraWorkflowEvent.id)).all()
        assert [event.outcome for event in approvals] == ["stale_draft", "accepted", "duplicate_approval"]
        decision = db.scalars(select(JiraWorkflowDecision).where(JiraWorkflowDecision.decision == "approve")).one()
        assert decision.draft_id == drafts[1].draft_id
        op = db.scalars(select(JiraWorkflowOperation).where(JiraWorkflowOperation.kind == "append_description")).one()
        jira = TrainingJira(db)
        assert jira.append_description(AppendDescription.model_validate(op.payload)).outcome == "already_applied"
        assert db.scalars(select(TrainingIssueWrite)).one()
        issue = jira.get_issue(training_run.issue_id, training_run.reporter_id)
        assert issue.status == training_run.status
        assert issue.description_text == training_run.description_text + "\n\n" + drafts[1].rendered_append
        assert db.scalars(select(JiraWorkflowOperation).where(
            JiraWorkflowOperation.operation_id == f"{RUN}:reply:confirm",
        )).one().status == "opened"
    assert calls[-1] == "result" and calls.count("result") == 1


async def test_dialogue_retry_after_worker_restart_has_one_operation(monkeypatch, training_run):
    _enable(monkeypatch)

    async def fails(*_):
        return AgentResult(status="timeout", error="agent timeout")

    await _tick(Worker(Deps(run_agent=fails)))
    with session_scope() as db:
        op = db.scalars(select(JiraWorkflowOperation)).one()
        assert op.status == "pending" and op.attempts == 1
    await _tick(Worker(Deps(run_agent=fails)))
    with session_scope() as db:
        op = db.scalars(select(JiraWorkflowOperation)).one()
        assert op.status == "failed" and op.attempts == 2
        assert db.get(JiraWorkflowRun, RUN).state == "needs_intervention"
