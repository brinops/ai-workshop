"""Thin GitHub REST client (PRs, check runs, job logs, annotations, webhook signatures)."""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import subprocess
from dataclasses import dataclass
from functools import lru_cache

import httpx

from app.config import get_settings
from app.services.registration import PRInfo

log = logging.getLogger("rcp.github")

REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class GitHubError(RuntimeError):
    pass


@dataclass
class CheckRun:
    id: int
    name: str
    status: str  # queued | in_progress | completed | waiting | requested | pending
    conclusion: str | None
    html_url: str | None
    details_url: str | None
    started_at: str | None
    completed_at: str | None
    app_slug: str | None

    def as_dict(self) -> dict:
        return self.__dict__.copy()


@lru_cache
def resolve_token() -> str | None:
    s = get_settings()
    if s.github_token:
        return s.github_token
    try:
        out = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def verify_webhook_signature(secret: str, body: bytes, signature_header: str | None) -> bool:
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


class GitHubClient:
    def __init__(self, token: str | None = None, base_url: str | None = None, transport: httpx.BaseTransport | None = None):
        self.token = token if token is not None else resolve_token()
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
                   "User-Agent": "ai-remediation-control-plane"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        self._client = httpx.Client(base_url=base_url or get_settings().github_api_url, headers=headers,
                                    timeout=20, follow_redirects=True, transport=transport)

    def close(self) -> None:
        self._client.close()

    def _get(self, path: str, **params) -> httpx.Response:
        try:
            resp = self._client.get(path, params=params or None)
        except httpx.HTTPError as exc:
            raise GitHubError(f"GET {path}: {exc}") from exc
        if resp.status_code >= 400:
            raise GitHubError(f"GET {path}: HTTP {resp.status_code} {resp.text[:200]}")
        return resp

    # ----------------------------------------------------------- pull requests
    def get_pr(self, repo: str, number: int) -> PRInfo:
        if not REPO_RE.match(repo):
            raise GitHubError(f"invalid repository name {repo!r}")
        d = self._get(f"/repos/{repo}/pulls/{number}").json()
        return pr_info_from_payload(repo, d)

    def get_branch_head(self, repo: str, branch: str) -> str:
        return self._get(f"/repos/{repo}/branches/{branch}").json()["commit"]["sha"]

    def get_pr_files(self, repo: str, number: int) -> list[dict]:
        files = self._get(f"/repos/{repo}/pulls/{number}/files", per_page=100).json()
        return [{"filename": f["filename"], "status": f["status"], "additions": f["additions"],
                 "deletions": f["deletions"]} for f in files]

    # ----------------------------------------------------------- checks
    def list_check_runs(self, repo: str, sha: str) -> list[CheckRun]:
        data = self._get(f"/repos/{repo}/commits/{sha}/check-runs", per_page=100, filter="latest").json()
        return [
            CheckRun(
                id=c["id"], name=c["name"], status=c["status"], conclusion=c.get("conclusion"),
                html_url=c.get("html_url"), details_url=c.get("details_url"),
                started_at=c.get("started_at"), completed_at=c.get("completed_at"),
                app_slug=(c.get("app") or {}).get("slug"),
            )
            for c in data.get("check_runs", [])
        ]

    def get_job_log(self, repo: str, job_id: int, max_bytes: int = 400_000) -> str:
        """For GitHub Actions the check run id equals the job id."""
        text = self._get(f"/repos/{repo}/actions/jobs/{job_id}/logs").text
        return text[-max_bytes:]

    def get_annotations(self, repo: str, check_run_id: int) -> list[dict]:
        return self._get(f"/repos/{repo}/check-runs/{check_run_id}/annotations", per_page=50).json()

    def ping(self) -> dict:
        resp = self._get("/user")
        return {"login": resp.json().get("login"), "scopes": resp.headers.get("x-oauth-scopes")}


def pr_info_from_payload(repo: str, d: dict) -> PRInfo:
    return PRInfo(
        repo=repo,
        number=d["number"],
        url=d["html_url"],
        title=d.get("title") or "",
        author=(d.get("user") or {}).get("login"),
        head_branch=d["head"]["ref"],
        head_sha=d["head"]["sha"],
        base_branch=d["base"]["ref"],
        state=d.get("state", "open"),
    )
