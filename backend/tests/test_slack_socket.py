import asyncio
import json

from fastapi.testclient import TestClient
from sqlalchemy import select

from app import main
from app.config import get_settings
from app.db import session_scope
from app.integrations import slack_socket, workshop_slack
from app.integrations.training_jira import TrainingJira
from app.models.jira_workflow import (
    JiraWorkflowDecision,
    JiraWorkflowDraft,
    JiraWorkflowEvent,
    JiraWorkflowOperation,
    JiraWorkflowProfile,
    JiraWorkflowRun,
)
from app.orchestration.worker import Worker


class Socket:
    def __init__(self, messages):
        self.messages = iter(messages)
        self.sent = []

    async def __aiter__(self):
        for message in self.messages:
            yield json.dumps(message)

    async def send(self, message):
        self.sent.append(json.loads(message))


async def test_local_socket_pairs_and_opens_one_thread_without_router(monkeypatch):
    monkeypatch.setenv("WORKSHOP_SLACK_APP_TOKEN", "xapp-test")
    monkeypatch.setenv("WORKSHOP_SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("WORKSHOP_SLACK_WORKSPACE_ID", "TWORK01")
    monkeypatch.setenv("WORKSHOP_SLACK_CHANNEL_ID", "CWORK01")
    monkeypatch.delenv("WORKSHOP_SLACK_ROUTER_URL", raising=False)
    monkeypatch.setenv("JIRA_WORKSHOP_POLL_INTERVAL_SECONDS", "0")
    get_settings.cache_clear()
    started = []

    async def listener(token, workspace):
        started.append((token, workspace))
        await asyncio.Future()

    sent = []

    def post(token, channel, reporter, request):
        sent.append((token, channel, reporter, request.issue_key))
        return "1794306000.000100"

    monkeypatch.setattr(main, "run_socket_mode", listener)
    monkeypatch.setattr(workshop_slack, "post_root", post)
    monkeypatch.setattr(workshop_slack, "permalink", lambda *_: "https://example.slack.com/archives/CWORK01/thread")
    with TestClient(main.create_app()) as client:
        pairing = "/api/jira/workshop/pairing"
        response = client.post(pairing)
        assert response.status_code == 200
        code = response.json()["code"]
        assert started == [("xapp-test", "TWORK01")]
        payload = {
            "type": "event_callback",
            "team_id": "TWORK01",
            "event": {"type": "message", "channel_type": "im", "user": "UWORK01", "text": f"pair {code}"},
        }
        messages = [
            {"type": "events_api", "envelope_id": "foreign", "payload": {**payload, "team_id": "TOTHER"}},
            {"type": "events_api", "envelope_id": "valid", "payload": payload},
            {"type": "events_api", "envelope_id": "repeat", "payload": payload},
        ]
        socket = Socket(messages)
        await slack_socket.receive_events(socket, "TWORK01")
        assert socket.sent == [{"envelope_id": message["envelope_id"]} for message in messages]

        profile = client.get(pairing).json()
        assert (profile["state"], profile["slack_user_id"]) == ("connected", "UWORK01")
        with session_scope() as db:
            issue = TrainingJira(db).create_booking_issue(profile["reporter_id"])
        await Worker().tick()
        await Worker().tick()
        with session_scope() as db:
            run = db.scalars(select(JiraWorkflowRun)).one()
            assert run.thread_url == "https://example.slack.com/archives/CWORK01/thread"
            assert db.scalars(select(JiraWorkflowOperation)).one().status == "opened"
        assert sent == [("xoxb-test", "CWORK01", "UWORK01", issue.issue_key)]


async def test_socket_routes_to_exact_thread_and_draft_and_deduplicates_redelivery():
    workspace, channel = "TWORK01", "CWORK01"
    root, other_root, draft_ts = "1794306000.000100", "1794306000.000200", "1794306001.000100"
    with session_scope() as db:
        db.add(JiraWorkflowProfile(
            profile_id="profile-01", local_instance_id="local-01",
            source_kind="training", source_instance_id="lab", source_reporter_id="reporter-01",
            slack_workspace_id=workspace, slack_user_id="UWORK01",
        ))
        db.flush()
        for run_id, issue_id, thread in (("run-1", "1", root), ("run-2", "2", other_root)):
            db.add(JiraWorkflowRun(
                run_id=run_id, profile_id="profile-01", source_kind="training", source_instance_id="lab",
                issue_id=issue_id, issue_key=f"LAB-{issue_id}", source_reporter_id="reporter-01",
                slack_workspace_id=workspace, slack_channel_id=channel, slack_thread_ts=thread, slack_user_id="UWORK01",
            ))
        db.flush()
        db.add(JiraWorkflowDraft(
            draft_id="draft-v2", run_id="run-1", version=2, based_on_description_revision="training:1:1",
            rendered_append="Уточнення", block={}, slack_message_ts=draft_ts,
        ))

    message = {
        "type": "message", "channel": channel, "thread_ts": root, "ts": "1794306002.000100",
        "user": "UWORK01", "text": "Залишалося одне місце.",
    }
    click = {
        "type": "block_actions", "team": {"id": workspace}, "user": {"id": "UWORK01"},
        "container": {"type": "message", "channel_id": channel, "message_ts": draft_ts},
        "actions": [{"action_id": "request_revision", "action_ts": "1794306003.000100",
                     "value": json.dumps({"draft_id": "draft-v2", "draft_version": 2})}],
    }

    def reply(event_id, **changes):
        return {"type": "event_callback", "team_id": workspace, "event_id": event_id, "event": {**message, **changes}}

    bad_version = {**click, "actions": [{**click["actions"][0], "value": '{"draft_id":"draft-v2","draft_version":1}'}]}
    bad_route = {**click, "container": {**click["container"], "thread_ts": other_root}}
    other_message = reply("EvOther", thread_ts=other_root)
    deliveries = [
        ("events_api", reply("EvReply")), ("events_api", reply("EvReply")),
        ("events_api", other_message), ("events_api", reply("EvBot", bot_id="BWORK01")),
        ("events_api", reply("EvForeign", user="UOTHER")),
        ("interactive", bad_version), ("interactive", bad_route), ("interactive", click), ("interactive", click),
    ]
    socket = Socket([{"type": kind, "envelope_id": str(i), "payload": payload}
                     for i, (kind, payload) in enumerate(deliveries)])
    await slack_socket.receive_events(socket, workspace)
    assert len(socket.sent) == len(deliveries)

    with session_scope() as db:
        events = db.scalars(select(JiraWorkflowEvent).order_by(JiraWorkflowEvent.id)).all()
        assert [(event.run_id, event.event_type) for event in events] == [
            ("run-1", "slack.thread_reply"), ("run-2", "slack.thread_reply"), ("run-1", "slack.draft_action"),
        ]
        action = events[-1].payload
        assert (action["draft_id"], action["draft_version"], action["message_ts"], action["action"]) == (
            "draft-v2", 2, draft_ts, "request_revision",
        )
        assert all(event.processed_at is None for event in events)
        assert db.get(JiraWorkflowRun, "run-1").state == "discovered"
        assert db.scalars(select(JiraWorkflowDecision)).first() is None
