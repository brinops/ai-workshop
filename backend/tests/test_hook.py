"""The Claude Code PostToolUse hook (`.claude/hooks/register_pr.py`)."""

from __future__ import annotations

import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "register_pr.py"
PR_URL = "https://github.com/acme/demo/pull/42"


def load_hook(monkeypatch, api_url: str, spool: Path):
    monkeypatch.setenv("RCP_API_URL", api_url)
    monkeypatch.setenv("RCP_SPOOL_FILE", str(spool))
    monkeypatch.delenv("RCP_AGENT", raising=False)
    spec = importlib.util.spec_from_file_location("register_pr", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    calls = []

    def fake_gh(args, cwd=None):
        calls.append(args)
        return {"number": 42, "url": PR_URL, "headRefName": "demo/x", "headRefOid": "a" * 40,
                "baseRefName": "main", "state": "OPEN", "title": "t"}

    monkeypatch.setattr(mod, "_gh", fake_gh)
    return mod, calls


@pytest.fixture
def backend():
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            received.append(body)
            out = json.dumps({"task_id": 1, "created": len(received) == 1, "state": "WAITING_CI"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", received
    server.shutdown()


def event(command: str, stdout: str = "") -> dict:
    return {"hook_event_name": "PostToolUse", "tool_name": "Bash", "cwd": "/tmp",
            "tool_input": {"command": command}, "tool_response": {"stdout": stdout, "stderr": "", "interrupted": False}}


def test_ignores_unrelated_commands(monkeypatch, tmp_path, backend, capsys):
    url, received = backend
    mod, calls = load_hook(monkeypatch, url, tmp_path / "spool.jsonl")
    for cmd in ["ls -la", "gh pr view 42", "git push", "echo 'gh pr created'"]:
        mod.handle_hook(event(cmd, PR_URL))
    mod.handle_hook({**event("gh pr create", PR_URL), "tool_name": "Read"})
    assert received == [] and calls == [] and capsys.readouterr().out == ""


def test_registers_created_pr(monkeypatch, tmp_path, backend, capsys):
    url, received = backend
    mod, calls = load_hook(monkeypatch, url, tmp_path / "spool.jsonl")
    mod.handle_hook(event('cd repo && gh pr create --title "x" --body "y"', f"Creating pull request\n{PR_URL}\n"))
    assert received == [{"repo": "acme/demo", "pr_number": 42, "pr_url": PR_URL, "head_sha": "a" * 40,
                         "head_branch": "demo/x", "source": "hook"}]
    assert calls[0][:3] == ["pr", "view", PR_URL]  # confirmed against GitHub
    out = json.loads(capsys.readouterr().out)
    assert "registered as task 1" in out["systemMessage"]


def test_agent_sessions_are_ignored(monkeypatch, tmp_path, backend):
    url, received = backend
    mod, _ = load_hook(monkeypatch, url, tmp_path / "spool.jsonl")
    monkeypatch.setenv("RCP_AGENT", "1")
    mod.handle_hook(event("gh pr create", PR_URL))
    assert received == []


def test_backend_down_spools_and_flushes(monkeypatch, tmp_path, backend, capsys):
    spool = tmp_path / "spool.jsonl"
    mod, _ = load_hook(monkeypatch, "http://127.0.0.1:9", spool)  # nothing listens on port 9
    mod.handle_hook(event("gh pr create", PR_URL))
    mod.handle_hook(event("gh pr create", PR_URL))  # duplicate stays a single spooled entry
    assert len(spool.read_text().splitlines()) == 1
    assert "queued" in json.loads(capsys.readouterr().out.splitlines()[-1])["systemMessage"]

    url, received = backend
    monkeypatch.setattr(mod, "API_URL", url)
    assert mod.main(["--flush"]) == 0
    assert len(received) == 1 and not spool.exists()


def test_never_raises(monkeypatch, tmp_path, capsys):
    mod, _ = load_hook(monkeypatch, "http://127.0.0.1:9", tmp_path / "s.jsonl")
    monkeypatch.setattr("sys.stdin", type("S", (), {"read": staticmethod(lambda: "{not json")})())
    assert mod.main([]) == 0
    assert "hook error ignored" in capsys.readouterr().out
