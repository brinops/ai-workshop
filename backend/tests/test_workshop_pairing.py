import hashlib
import hmac
import json
from datetime import timedelta
from time import time
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api import workshop_pairing
from app.config import get_settings
from app.db import get_engine, init_engine, session_scope, utcnow
from app.integrations.training_jira import TrainingJira
from app.main import create_app
from app.models.jira_workflow import JiraWorkflowDraft, JiraWorkflowOperation, JiraWorkflowProfile, JiraWorkflowRun
from app.models.slack_pairing import SlackPairing
from app.orchestration.worker import Worker
from app.services.workshop_pairing import local_identity
from app.services.workshop_replies import enqueue_reply
from app.slack_router import app as shared_router

LOCAL = "/api/jira/workshop/pairing"
SECRET = "test-signing-secret"
WORKSPACE = "TWORK01"


def _event(code, *, user="UWORK01", workspace=WORKSPACE, channel_type="im"):
    return {
        "type": "event_callback",
        "team_id": workspace,
        "event": {"type": "message", "channel_type": channel_type, "user": user, "text": f"pair {code}"},
    }


def _send(router, payload, *, secret=SECRET, timestamp=None):
    body = json.dumps(payload).encode()
    stamp = str(int(time()) if timestamp is None else timestamp)
    signature = hmac.new(secret.encode(), b"v0:" + stamp.encode() + b":" + body, hashlib.sha256)
    return router.post("/slack/events", content=body, headers={
        "X-Slack-Request-Timestamp": stamp,
        "X-Slack-Signature": f"v0={signature.hexdigest()}",
    })


def _configure(monkeypatch, router):
    monkeypatch.setenv("WORKSHOP_SLACK_ROUTER_URL", "https://router.test")
    monkeypatch.setenv("WORKSHOP_SLACK_SIGNING_SECRET", SECRET)
    monkeypatch.setenv("WORKSHOP_SLACK_WORKSPACE_ID", WORKSPACE)
    monkeypatch.setenv("JIRA_WORKSHOP_POLL_INTERVAL_SECONDS", "0")
    get_settings.cache_clear()

    def transport(request):
        return router.request(request.method, request.url.path, headers=request.headers, content=request.content)

    def client(**kwargs):
        return httpx.Client(transport=httpx.MockTransport(transport), **kwargs)

    monkeypatch.setattr(workshop_pairing, "httpx", SimpleNamespace(Client=client, HTTPError=httpx.HTTPError))


async def test_pairing_activates_scheduler_and_survives_restart(monkeypatch):
    with TestClient(shared_router) as router:
        _configure(monkeypatch, router)
        with TestClient(create_app()) as local:
            assert local.get(LOCAL).json()["state"] == "idle"
            started = local.post(LOCAL)
            code = started.json()["code"]
            assert started.headers["cache-control"] == "no-store"
            assert local.get(LOCAL).json()["state"] == "pending"
            with session_scope() as db:
                assert db.scalars(select(JiraWorkflowProfile)).first() is None
                identity = local_identity(db)
                assert identity["token"] not in started.text
            status_url = f"/pairings/{identity['instance_id']}"
            assert router.get(status_url, headers={"Authorization": "Bearer " + "x" * 43}).status_code == 401

            assert _send(router, _event(code), secret="wrong").status_code == 401
            assert _send(router, _event(code), timestamp=int(time()) - 301).status_code == 401
            assert _send(router, _event(code, workspace="TOTHER")).json()["paired"] is False
            assert _send(router, _event(code, channel_type="channel")).json()["paired"] is False
            assert _send(router, _event(code)).json()["paired"] is True
            assert _send(router, _event(code, user="UWORK02")).json()["paired"] is False
            profile = local.get(LOCAL).json()
            assert profile["state"] == "connected" and profile["slack_user_id"] == "UWORK01"
            assert profile["code"] is None and local.post(LOCAL).json() == profile

            with session_scope() as db:
                jira = TrainingJira(db)
                issue = jira.create_booking_issue(profile["reporter_id"])
                jira.create_booking_issue("other-reporter")
                assert len(db.scalars(select(JiraWorkflowProfile)).all()) == 1

            engine = get_engine()
            url = str(engine.url)
            engine.dispose()
            init_engine(url)
            assert local.get(LOCAL).json() == profile
            monkeypatch.delenv("WORKSHOP_SLACK_ROUTER_URL")
            get_settings.cache_clear()
            await Worker().tick()
            with session_scope() as db:
                run = db.scalars(select(JiraWorkflowRun)).one()
                assert (run.issue_id, run.profile_id, run.slack_user_id) == (
                    issue.issue_id, profile["profile_id"], "UWORK01",
                )
                assert db.scalars(select(JiraWorkflowOperation)).one().status == "pending"


def test_expired_code_can_be_replaced_and_consumed_only_once(monkeypatch):
    with TestClient(shared_router) as router:
        _configure(monkeypatch, router)
        with TestClient(create_app()) as local:
            old_code = local.post(LOCAL).json()["code"]
            with session_scope() as db:
                db.scalars(select(SlackPairing)).one().expires_at = utcnow() - timedelta(seconds=1)
            assert _send(router, _event(old_code)).json()["paired"] is False
            assert local.get(LOCAL).json()["state"] == "expired"
            new_code = local.post(LOCAL).json()["code"]
            assert new_code != old_code
            assert _send(router, _event(old_code)).json()["paired"] is False
            assert _send(router, _event(new_code)).json()["paired"] is True
            assert local.get(LOCAL).json()["slack_user_id"] == "UWORK01"


def _configure_threads(monkeypatch, router, slack_handler, *, lose_first_receipt=False):
    from app.integrations import workshop_slack
    from app.orchestration import slack_inbox_poll, slack_thread_queue

    _configure(monkeypatch, router)
    monkeypatch.setenv("WORKSHOP_SLACK_CHANNEL_ID", "CWORK01")
    monkeypatch.setenv("WORKSHOP_SLACK_BOT_TOKEN", "test-bot-token")
    get_settings.cache_clear()

    def slack_client(**kwargs):
        return httpx.Client(transport=httpx.MockTransport(slack_handler), **kwargs)

    forwarded = []

    def router_transport(request):
        is_thread = "/threads/" in request.url.path
        if is_thread:
            forwarded.append(request)
        response = router.request(request.method, request.url.path, headers=request.headers, content=request.content)
        if is_thread and lose_first_receipt and len(forwarded) == 1:
            raise httpx.ReadTimeout("lost the completed router response")
        return httpx.Response(response.status_code, content=response.content, headers=response.headers)

    def router_client(**kwargs):
        return httpx.AsyncClient(transport=httpx.MockTransport(router_transport), **kwargs)

    monkeypatch.setattr(workshop_slack, "httpx", SimpleNamespace(Client=slack_client))
    monkeypatch.setattr(slack_thread_queue, "httpx", SimpleNamespace(AsyncClient=router_client, HTTPError=httpx.HTTPError))
    monkeypatch.setattr(slack_inbox_poll, "httpx", SimpleNamespace(AsyncClient=router_client))
    return forwarded


def _paired_issue(local, router):
    code = local.post(LOCAL).json()["code"]
    assert _send(router, _event(code)).json()["paired"]
    profile = local.get(LOCAL).json()
    with session_scope() as db:
        return TrainingJira(db).create_booking_issue(profile["reporter_id"])


async def test_thread_opening_survives_lost_router_receipt_without_duplicate(monkeypatch):
    slack_calls = []
    link = "https://workshop-example.slack.com/archives/CWORK01/p1794306000000100"

    def slack_handler(request):
        slack_calls.append(request)
        assert request.headers["Authorization"] == "Bearer test-bot-token"
        if request.url.path.endswith("/chat.postMessage"):
            payload = json.loads(request.content)
            assert payload["channel"] == "CWORK01"
            assert "<@UWORK01>" in payload["text"] and "Навчальна Jira" in payload["text"]
            assert "LAB-1" in payload["text"] and "thread_ts" not in payload
            return httpx.Response(200, json={"ok": True, "channel": "CWORK01", "ts": "1794306000.000100"})
        assert request.url.path.endswith("/chat.getPermalink")
        assert request.url.params == httpx.QueryParams({"channel": "CWORK01", "message_ts": "1794306000.000100"})
        return httpx.Response(200, json={"ok": True, "permalink": link})

    with TestClient(shared_router) as router:
        forwarded = _configure_threads(monkeypatch, router, slack_handler, lose_first_receipt=True)
        with TestClient(create_app()) as local:
            issue = _paired_issue(local, router)
            worker = Worker()
            await worker.tick()
            with session_scope() as db:
                assert db.scalars(select(JiraWorkflowOperation)).one().status == "pending"
                assert db.scalars(select(JiraWorkflowRun)).one().thread_url is None
            engine = get_engine()
            url = str(engine.url)
            engine.dispose()
            init_engine(url)
            await Worker().tick()
            await Worker().tick()

            with session_scope() as db:
                run = db.scalars(select(JiraWorkflowRun)).one()
                assert (run.issue_id, run.slack_workspace_id, run.slack_channel_id) == (issue.issue_id, WORKSPACE, "CWORK01")
                assert (run.slack_thread_ts, run.thread_url) == ("1794306000.000100", link)
                op = db.scalars(select(JiraWorkflowOperation)).one()
                assert op.status == "opened" and op.attempts == 2
            assert len(forwarded) == 2
            assert forwarded[0].url == forwarded[1].url and forwarded[0].content == forwarded[1].content
            assert [request.url.path for request in slack_calls] == ["/api/chat.postMessage", "/api/chat.getPermalink"]
            first = forwarded[0]
            tampered = {**json.loads(first.content), "reporter_slack_user_id": "UWORK02"}
            assert router.put(first.url.path, headers=first.headers, json=tampered).status_code == 403


async def test_unconfirmed_slack_post_is_never_resent(monkeypatch):
    calls = []

    def slack_handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("Slack may already have posted")

    with TestClient(shared_router) as router:
        forwarded = _configure_threads(monkeypatch, router, slack_handler)
        with TestClient(create_app()) as local:
            _paired_issue(local, router)
            await Worker().tick()
            first = forwarded[0]
            repeated = router.put(first.url.path, headers=first.headers, content=first.content)
            assert repeated.json()["state"] == "unknown"
            await Worker().tick()

            with session_scope() as db:
                op = db.scalars(select(JiraWorkflowOperation)).one()
                run = db.scalars(select(JiraWorkflowRun)).one()
                assert op.status == "unknown" and op.result["reason"] == "slack_post_unconfirmed"
                assert run.state == "needs_intervention" and run.thread_url is None
            assert len(calls) == 1


async def test_permalink_retry_does_not_resend_root_message(monkeypatch):
    methods = []

    def slack_handler(request):
        method = request.url.path.rsplit("/", 1)[-1]
        methods.append(method)
        if method == "chat.postMessage":
            return httpx.Response(200, json={"ok": True, "channel": "CWORK01", "ts": "1794306000.000100"})
        if methods.count("chat.getPermalink") == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True, "permalink": "https://workshop-example.slack.com/archives/thread"})

    with TestClient(shared_router) as router:
        _configure_threads(monkeypatch, router, slack_handler)
        with TestClient(create_app()) as local:
            _paired_issue(local, router)
            worker = Worker()
            await worker.tick()
            with session_scope() as db:
                assert db.scalars(select(JiraWorkflowOperation)).one().result["reason"] == "permalink_unavailable"
            await worker.tick()
            with session_scope() as db:
                assert db.scalars(select(JiraWorkflowOperation)).one().status == "opened"
            assert methods == ["chat.postMessage", "chat.getPermalink", "chat.getPermalink"]


async def test_plain_reply_and_versioned_draft_use_existing_thread_and_deduplicate(monkeypatch):
    posts = []
    parent_ts = "1794306000.000100"
    rendered = "Фактично: <обидва> отримали підтвердження.\nОчікування: другий у листі очікування."

    def slack_handler(request):
        if request.url.path.endswith("chat.postMessage"):
            payload = json.loads(request.content)
            posts.append(payload)
            ts = parent_ts if len(posts) == 1 else f"1794306000.000{len(posts)}00"
            return httpx.Response(200, json={"ok": True, "channel": "CWORK01", "ts": ts})
        return httpx.Response(200, json={"ok": True, "permalink": "https://example.slack.com/thread"})

    with TestClient(shared_router) as router:
        forwarded = _configure_threads(monkeypatch, router, slack_handler)
        with TestClient(create_app()) as local:
            _paired_issue(local, router)
            worker = Worker()
            await worker.tick()
            with session_scope() as db:
                run = db.scalars(select(JiraWorkflowRun)).one()
                db.add(JiraWorkflowDraft(
                    draft_id="draft-lab-v2", run_id=run.run_id, version=2,
                    based_on_description_revision="training:1:1", rendered_append=rendered, block={},
                ))
                enqueue_reply(db, run.run_id, "clarification", "Скільки місць залишалося?")
                op_id = enqueue_reply(db, run.run_id, "draft-v2", "Перевір деталі.", draft_id="draft-lab-v2")
                assert enqueue_reply(db, run.run_id, "draft-v2", "Перевір деталі.", draft_id="draft-lab-v2") == op_id
                with pytest.raises(ValueError, match="different content"):
                    enqueue_reply(db, run.run_id, "draft-v2", "Інший текст.", draft_id="draft-lab-v2")

            await worker.tick()
            await worker.tick()
            await worker.tick()
            assert len(posts) == 3
            plain, draft = posts[1:]
            assert plain["thread_ts"] == draft["thread_ts"] == parent_ts
            assert plain["text"] == "Скільки місць залишалося?" and plain["mrkdwn"] is False
            assert draft["blocks"][1]["text"] == {"type": "plain_text", "text": f"Чернетка v2\n{rendered}"}
            buttons = draft["blocks"][-1]["elements"]
            assert [(b["action_id"], b["text"]["text"]) for b in buttons] == [
                ("approve", "Схвалити"), ("request_revision", "Попросити правки"),
            ]
            assert all(json.loads(b["value"]) == {"draft_id": "draft-lab-v2", "draft_version": 2} for b in buttons)

            delivery = forwarded[-1]
            assert router.put(delivery.url.path, headers=delivery.headers, content=delivery.content).json()["state"] == "opened"
            assert len(posts) == 3
            with session_scope() as db:
                run = db.scalars(select(JiraWorkflowRun)).one()
                assert run.slack_thread_ts == parent_ts
                assert db.get(JiraWorkflowDraft, "draft-lab-v2").slack_message_ts == "1794306000.000300"
                assert db.get(JiraWorkflowOperation, op_id).status == "opened"
