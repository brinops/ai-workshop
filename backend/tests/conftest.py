from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from app import db as dbmod
from app.config import get_settings
from app.integrations.claude_runner import AgentResult
from app.integrations.git_worktree import ChangedFile
from app.integrations.github import CheckRun, resolve_token
from app.orchestration.worker import Deps, Worker
from app.services.registration import PRInfo


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "var"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'var' / 'test.db'}")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "")
    monkeypatch.setenv("RCP_API_TOKEN", "")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("RUN_WORKER", "false")
    monkeypatch.setenv("CI_POLL_INTERVAL_SECONDS", "0")
    monkeypatch.setenv("HEARTBEAT_SECONDS", "1")
    get_settings.cache_clear()
    resolve_token.cache_clear()
    dbmod.run_migrations()
    dbmod.init_engine()
    yield
    get_settings.cache_clear()
    resolve_token.cache_clear()


SHA1 = "a" * 40
SHA_FIX = "f" * 40


def pr_info(sha: str = SHA1, number: int = 7) -> PRInfo:
    return PRInfo(repo="acme/demo", number=number, url=f"https://github.com/acme/demo/pull/{number}",
                  title="Change values", author="dev", head_branch="demo/x", head_sha=sha, base_branch="main")


FINDING = {"category": "LOGICAL_CONFIGURATION_ERROR", "check": "service-target-port",
           "message": "targetPort 9090 does not match", "chart": "demo/charts/payments-api",
           "file": "demo/charts/payments-api/templates/service.yaml", "line": None, "resource": "Service/x"}


class FakeGitHub:
    """In-memory GitHub: check-run verdicts per SHA, a PR head, and a job log with RCP findings."""

    def __init__(self):
        self.checks: dict[str, list[CheckRun]] = {}
        self.pr_head = SHA1
        self.pr_state = "open"
        self.log = "2024-01-01T00:00:00.0000000Z ##[error]boom\n2024-01-01T00:00:00Z RCP-FINDING " + \
            __import__("json").dumps(FINDING)

    def set_check(self, sha: str, status: str, conclusion: str | None, name: str = "helm-validate") -> None:
        cid = len([c for v in self.checks.values() for c in v]) + 100
        self.checks.setdefault(sha, []).append(CheckRun(cid, name, status, conclusion, "https://gh/run", None,
                                                        None, None, "github-actions"))

    def list_check_runs(self, repo, sha):
        return list(self.checks.get(sha, []))

    def get_job_log(self, repo, job_id, max_bytes=0):
        return self.log

    def get_annotations(self, repo, cid):
        return [{"path": "demo/charts/payments-api/values.yaml", "start_line": 20, "title": "x", "message": "m",
                 "annotation_level": "failure"}]

    def get_pr_files(self, repo, number):
        return [{"filename": "demo/charts/payments-api/values.yaml", "status": "modified", "additions": 1, "deletions": 1}]

    def get_pr(self, repo, number):
        return PRInfo(repo=repo, number=number, url="u", title="t", author="dev", head_branch="demo/x",
                      head_sha=self.pr_head, base_branch="main", state=self.pr_state)

    def close(self):
        pass


@dataclass
class FakeWorktrees:
    root: Path
    changed: list[ChangedFile] = field(default_factory=lambda: [ChangedFile("demo/charts/payments-api/values.yaml", "M", 1, 1)])
    pushes: list[tuple[str, str]] = field(default_factory=list)
    commit_sha: str = SHA_FIX
    github: FakeGitHub | None = None

    async def fetch_pr(self, repo, number, head, base):
        return self.root

    async def create(self, repo, task_id, label, sha):
        p = self.root / f"task-{task_id}-{label}"
        (p / "demo" / "charts" / "payments-api").mkdir(parents=True, exist_ok=True)
        (p / "demo" / "charts" / "payments-api" / "Chart.yaml").write_text("name: x\n")
        return p

    async def remove(self, repo, path):
        pass

    async def diff_against(self, wt, base, head="HEAD"):
        return "-  targetPort: 8080\n+  targetPort: 9090\n"

    async def working_changes(self, wt):
        return "--- a/v\n+++ b/v\n-  targetPort: 9090\n+  targetPort: 8080\n", self.changed

    async def commit(self, wt, message):
        return self.commit_sha

    async def push(self, wt, branch):
        self.pushes.append((str(wt), branch))
        if self.github:
            self.github.pr_head = self.commit_sha


ANALYSIS_OK = {
    "classification": "LOGICAL_CONFIGURATION_ERROR",
    "root_cause": "service.targetPort was changed to 9090 but the app listens on 8080",
    "affected_files": [{"path": "demo/charts/payments-api/values.yaml", "line": 20, "reason": "wrong targetPort"}],
    "evidence": [{"source": "validator", "detail": "service-target-port finding"}],
    "proposed_fix": {"summary": "Restore targetPort 8080", "steps": ["set service.targetPort to 8080"],
                     "changes": [{"file": "demo/charts/payments-api/values.yaml", "description": "9090 → 8080"}]},
    "confidence": 0.93,
    "auto_remediation_appropriate": True,
    "auto_remediation_rationale": "unambiguous",
    "markdown": "The Service routes to a port nothing listens on.",
}
REMEDIATION_OK = {
    "status": "fixed", "summary": "Restored service.targetPort to 8080",
    "changes": [{"file": "demo/charts/payments-api/values.yaml", "description": "9090 → 8080"}],
    "rationale": "app.port is 8080", "validation": {"ran": True, "passed": True, "summary": "VALID"},
}


class FakeAgents:
    def __init__(self):
        self.calls: list[str] = []
        self.analysis = dict(ANALYSIS_OK)
        self.remediation = dict(REMEDIATION_OK)
        self.block = False  # wait for cancellation instead of returning

    async def __call__(self, spec, emit, cancel, on_start=None):
        kind = "remediation" if spec.agent else "analysis"
        self.calls.append(kind)
        if on_start:
            on_start(12345)
        emit("system", f"fake {kind} started")
        if self.block:
            await cancel.wait()
            return AgentResult(status="cancelled", error="agent cancelled")
        return AgentResult(status="succeeded", structured=self.analysis if kind == "analysis" else self.remediation,
                           cost_usd=0.01, num_turns=3)


@dataclass
class Harness:
    worker: Worker
    github: FakeGitHub
    worktrees: FakeWorktrees
    agents: FakeAgents
    slack: list
    validate_results: list

    async def drain(self, rounds: int = 8) -> None:
        for _ in range(rounds):
            await self.worker.tick()
            jobs = [r.job for r in self.worker.running.values() if r.job]
            if jobs:
                await asyncio.gather(*jobs, return_exceptions=True)


@pytest.fixture
def harness(tmp_path) -> Harness:
    gh = FakeGitHub()
    wts = FakeWorktrees(tmp_path / "wt", github=gh)
    agents = FakeAgents()
    slack_calls: list = []
    validate_results: list = []

    async def fake_validate(worktree, charts):
        if validate_results:
            return validate_results.pop(0)
        return {"valid": True, "charts": [], "exit_code": 0}

    async def fake_slack(payload):
        slack_calls.append(payload)
        return "sent", None

    worker = Worker(Deps(github=lambda: gh, worktrees=wts, run_agent=agents, validate=fake_validate,
                         slack_send=fake_slack), worker_id="test-worker")
    return Harness(worker, gh, wts, agents, slack_calls, validate_results)
