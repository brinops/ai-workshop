import json
from contextlib import contextmanager
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import get_db, get_engine, init_engine, run_migrations, session_scope, utcnow
from app.integrations.slack_socket import receive_events
from app.models.jira_workflow import JiraWorkflowDraft, JiraWorkflowEvent, JiraWorkflowRun
from app.models.slack_pairing import SlackPairing
from app.models.slack_thread import SlackThreadOpening
from app.orchestration import slack_inbox_poll
from app.services import slack_routing
from app.services.workshop_pairing import activate_training_profile, local_identity
from app.slack_router import app, digest

WORKSPACE = "TWORK01"
CHANNEL = "CWORK01"
ROUTER_URL = "https://private-router.test"


class Socket:
    def __init__(self, envelopes):
        self.envelopes = envelopes
        self.acks = []

    async def __aiter__(self):
        for envelope in self.envelopes:
            yield json.dumps(envelope)

    async def send(self, message):
        self.acks.append(json.loads(message)["envelope_id"])


def _local_instance(url, number):
    run_migrations(url)
    init_engine(url)
    actor = f"UWORK0{number}"
    root_ts = f"1794306000.000{number}00"
    draft_ts = f"1794306001.000{number}00"
    with session_scope() as db:
        identity = local_identity(db, create=True)
        profile = activate_training_profile(db, identity["instance_id"], WORKSPACE, actor)
        run = JiraWorkflowRun(
            run_id=f"run-{number}", profile_id=profile.profile_id, issue_id="1", issue_key="LAB-1",
            source_kind=profile.source_kind, source_instance_id=profile.source_instance_id,
            source_reporter_id=profile.source_reporter_id, slack_user_id=actor,
            slack_workspace_id=WORKSPACE, slack_channel_id=CHANNEL, slack_thread_ts=root_ts,
        )
        db.add(run)
        db.flush()
        db.add(JiraWorkflowDraft(
            draft_id=f"draft-{number}", run_id=run.run_id, version=number,
            based_on_description_revision="training:1:1", rendered_append="Уточнення", block={},
            slack_message_ts=draft_ts,
        ))
    return identity, actor, root_ts, draft_ts


def _events(instance, number):
    _, actor, root, draft = instance
    return [
        {"type": "events_api", "envelope_id": f"envelope-reply-{number}", "payload": {
            "type": "event_callback", "event_id": f"EvReply{number}", "team_id": WORKSPACE,
            "event": {"type": "message", "channel": CHANNEL, "thread_ts": root,
                      "ts": f"1794306002.000{number}00", "user": actor, "text": f"reply-{number}"},
        }},
        {"type": "interactive", "envelope_id": f"envelope-click-{number}", "payload": {
            "type": "block_actions", "team": {"id": WORKSPACE}, "user": {"id": actor},
            "container": {"type": "message", "channel_id": CHANNEL, "message_ts": draft},
            "actions": [{"action_id": "request_revision", "action_ts": f"1794306003.000{number}00",
                         "value": json.dumps({"draft_id": f"draft-{number}", "draft_version": number})}],
        }},
    ]


async def test_private_router_isolates_two_databases_and_replays_after_lost_ack(tmp_path, monkeypatch):
    local_urls = [f"sqlite:///{tmp_path / f'local-{n}.db'}" for n in (1, 2)]
    instances = [_local_instance(url, n) for n, url in enumerate(local_urls, 1)]
    hub_url = f"sqlite:///{tmp_path / 'hub.db'}"
    run_migrations(hub_url)
    hub = create_engine(hub_url)
    hub_factory = sessionmaker(hub, expire_on_commit=False)

    @contextmanager
    def hub_session():
        with hub_factory.begin() as db:
            yield db

    def hub_db():
        with hub_session() as db:
            yield db

    monkeypatch.setattr(slack_routing, "session_scope", hub_session)
    monkeypatch.setitem(app.dependency_overrides, get_db, hub_db)
    with hub_session() as db:
        for n, (identity, actor, root, draft) in enumerate(instances, 1):
            db.add(SlackPairing(instance_id=identity["instance_id"], token_digest=digest(identity["token"]),
                                expires_at=utcnow(), workspace_id=WORKSPACE, slack_user_id=actor))
            db.add_all([
                SlackThreadOpening(instance_id=identity["instance_id"], operation_id=f"run-{n}:thread",
                                   request_digest="root", channel_id=CHANNEL, started_at=utcnow(),
                                   state="posted", thread_ts=root),
                SlackThreadOpening(instance_id=identity["instance_id"], operation_id=f"run-{n}:draft:draft-{n}",
                                   request_digest="draft", channel_id=CHANNEL, started_at=utcnow(),
                                   state="posted", thread_ts=draft, draft_version=n),
            ])
    envelopes = [item for n, instance in enumerate(instances, 1) for item in _events(instance, n)]
    first_socket = Socket(envelopes)
    await receive_events(first_socket, WORKSPACE, shared=True)
    assert len(first_socket.acks) == 4
    hub.dispose()

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ROUTER_URL) as router:
        credentials = [(f"/pairings/{i['instance_id']}/inbox", {"Authorization": f"Bearer {i['token']}"})
                       for i, *_ in instances]
        (a_path, a_headers), (b_path, b_headers) = credentials
        assert (await router.get(b_path, headers=a_headers)).status_code == 401
        a_events = (await router.get(a_path, headers=a_headers)).json()
        b_events = (await router.get(b_path, headers=b_headers)).json()
        assert [event["run_id"] for event in a_events] == ["run-1", "run-1"]
        assert [event["run_id"] for event in b_events] == ["run-2", "run-2"]
        assert (await router.post(a_path + "/ack", headers=a_headers,
                                  json={"event_ids": [b_events[0]["event_id"]]})).status_code == 204
        assert (await router.get(b_path, headers=b_headers)).json() == b_events
        lost_ack = False

        async def forward(request):
            nonlocal lost_ack
            if request.url.path == a_path + "/ack" and not lost_ack:
                lost_ack = True
                raise httpx.ConnectError("local instance disconnected before acknowledgement")
            result = await router.request(request.method, request.url.path, headers=request.headers,
                                          content=request.content)
            return httpx.Response(result.status_code, content=result.content, headers=result.headers)

        monkeypatch.setattr(slack_inbox_poll, "httpx", SimpleNamespace(
            AsyncClient=lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(forward), **kwargs),
        ))
        init_engine(local_urls[0])
        with pytest.raises(httpx.ConnectError):
            await slack_inbox_poll.poll_slack_inbox(ROUTER_URL)
        assert (await router.get(a_path, headers=a_headers)).json() == a_events
        with session_scope() as db:
            assert len(db.scalars(select(JiraWorkflowEvent)).all()) == 2
        get_engine().dispose()
        init_engine(local_urls[0])

        second_socket = Socket([{**event, "envelope_id": f"retry-{i}"} for i, event in enumerate(envelopes)])
        await receive_events(second_socket, WORKSPACE, shared=True)
        assert len(second_socket.acks) == 4
        for n, url in enumerate(local_urls, 1):
            init_engine(url)
            await slack_inbox_poll.poll_slack_inbox(ROUTER_URL)
            await slack_inbox_poll.poll_slack_inbox(ROUTER_URL)
            with session_scope() as db:
                rows = db.scalars(select(JiraWorkflowEvent).order_by(JiraWorkflowEvent.id)).all()
                assert [(row.run_id, row.event_type) for row in rows] == [
                    (f"run-{n}", "slack.thread_reply"), (f"run-{n}", "slack.draft_action"),
                ]
                assert rows[1].payload["draft_version"] == n
            path, headers = credentials[n - 1]
            assert (await router.get(path, headers=headers)).json() == []
        await receive_events(Socket(envelopes), WORKSPACE, shared=True)
        assert (await router.get(a_path, headers=a_headers)).json() == []
        assert (await router.get(b_path, headers=b_headers)).json() == []
    hub.dispose()
