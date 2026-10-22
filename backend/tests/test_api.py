from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from app.integrations import github as gh_mod
from app.main import create_app
from tests.conftest import SHA1, pr_info


@pytest.fixture
def client(monkeypatch):
    class StubGitHub:
        def __init__(self, *a, **k):
            pass

        def get_pr(self, repo, number):
            if number == 404:
                raise gh_mod.GitHubError("HTTP 404")
            return pr_info(number=number)

        def close(self):
            pass

    monkeypatch.setattr("app.api.routes.GitHubClient", StubGitHub)
    with TestClient(create_app()) as c:
        yield c


def test_register_dedup_and_board(client):
    body = {"repo": "acme/demo", "pr_number": 7, "head_sha": SHA1, "source": "hook"}
    r1 = client.post("/api/tasks/register", json=body)
    r2 = client.post("/api/tasks/register", json=body)
    assert r1.status_code == 200 and r1.json()["created"] is True
    assert r2.json() == {**r1.json(), "created": False}
    board = client.get("/api/board").json()
    assert board["counts"]["NEW"] == 1 and board["state_counts"]["WAITING_CI"] == 1
    card = board["columns"]["NEW"][0]
    assert card["column"] == "NEW" and card["created_at"].endswith("Z")


@pytest.mark.parametrize("body", [
    {"repo": "not a repo", "pr_number": 1},
    {"repo": "acme/demo", "pr_number": 0},
    {"repo": "acme/demo", "pr_number": 1, "head_sha": "zzz"},
    {"repo": "acme/demo", "pr_number": 1, "source": "evil"},
])
def test_register_validates_input(client, body):
    assert client.post("/api/tasks/register", json=body).status_code == 422


def test_register_requires_confirmed_pr(client):
    assert client.post("/api/tasks/register", json={"repo": "acme/demo", "pr_number": 404}).status_code == 502


def test_register_token(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("RCP_API_TOKEN", "s3cret-token")
    get_settings.cache_clear()
    body = {"repo": "acme/demo", "pr_number": 7}
    assert client.post("/api/tasks/register", json=body).status_code == 401
    ok = client.post("/api/tasks/register", json=body, headers={"Authorization": "Bearer s3cret-token"})
    assert ok.status_code == 200


def test_task_detail_and_actions(client):
    tid = client.post("/api/tasks/register", json={"repo": "acme/demo", "pr_number": 7}).json()["task_id"]
    detail = client.get(f"/api/tasks/{tid}").json()
    assert detail["task"]["state"] == "WAITING_CI"
    assert set(detail["actions"]) == {"pause", "cancel", "mark_review"}
    assert [e["type"] for e in detail["events"]][:2] == ["registered", "state_changed"]

    assert client.post(f"/api/tasks/{tid}/actions/approve_push").status_code == 409
    assert client.post(f"/api/tasks/{tid}/actions/explode").status_code == 422
    r = client.post(f"/api/tasks/{tid}/actions/pause")
    assert r.status_code == 200 and r.json()["task"]["paused"] is True
    assert "resume" in client.get(f"/api/tasks/{tid}").json()["actions"]
    r = client.post(f"/api/tasks/{tid}/actions/cancel")
    assert r.json()["task"]["state"] == "FAILED"
    assert "retry" in client.get(f"/api/tasks/{tid}").json()["actions"]
    assert client.get("/api/tasks/999").status_code == 404


def test_automation_settings_persist(client):
    assert client.get("/api/settings/automation").json()["auto_push"] is False  # safe default
    r = client.put("/api/settings/automation", json={"auto_push": True})
    assert r.json() == {"auto_analyze": True, "auto_remediate": True, "auto_push": True}
    assert client.get("/api/settings/automation").json()["auto_push"] is True
    assert any(e["type"] == "settings_changed" for e in client.get("/api/events").json())


def test_github_webhook_signature_and_convergence(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "whsec")
    get_settings.cache_clear()
    payload = {
        "action": "opened",
        "repository": {"full_name": "acme/demo"},
        "pull_request": {"number": 9, "html_url": "https://github.com/acme/demo/pull/9", "title": "t",
                         "user": {"login": "dev"}, "head": {"ref": "demo/y", "sha": SHA1}, "base": {"ref": "main"},
                         "state": "open"},
    }
    raw = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(b"whsec", raw, hashlib.sha256).hexdigest()
    headers = {"X-GitHub-Event": "pull_request", "Content-Type": "application/json"}
    assert client.post("/api/webhooks/github", content=raw, headers={**headers, "X-Hub-Signature-256": "sha256=bad"}).status_code == 401
    r = client.post("/api/webhooks/github", content=raw, headers={**headers, "X-Hub-Signature-256": sig})
    assert r.json()["created"] is True
    # The hook path for the same PR converges on the same task.
    r2 = client.post("/api/tasks/register", json={"repo": "acme/demo", "pr_number": 9})
    assert r2.json()["task_id"] == r.json()["task_id"] and r2.json()["created"] is False


def test_health(client):
    h = client.get("/api/health").json()
    assert h["components"]["database"]["ok"] is True
    assert h["components"]["slack"]["ok"] is False
    assert h["repositories"] == ["acme/demo"]


def test_unconfigured_repository_is_rejected(client):
    assert client.post("/api/tasks/register", json={"repo": "acme/other", "pr_number": 1}).status_code == 403


def test_config_endpoint(client):
    cfg = client.get("/api/config").json()
    route = cfg["repositories"][0]["routes"][0]
    assert route["check"] == "helm-validate" and route["remediation_agent"] == "k8s-remediator"
