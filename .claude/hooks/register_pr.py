#!/usr/bin/env python3
"""Claude Code PostToolUse hook: register PRs created with `gh pr create` in the Remediation Control Plane.

Behaviour
  * Fires on every Bash tool use (matcher "Bash") but acts only when the command contains `gh pr create`
    AND the PR can be resolved — other tool executions are ignored.
  * Resolves the PR URL from the command output (fallback: `gh pr view` for the current branch),
    then confirms it exists via `gh pr view --json`.
  * POSTs an idempotent registration to $RCP_API_URL/api/tasks/register (the backend de-duplicates
    on repo + PR number and re-verifies the PR against GitHub itself).
  * Never blocks or fails the developer's workflow: always exits 0. If the backend is down, the
    registration is spooled to ~/.cache/rcp/pending-registrations.jsonl and retried on the next
    invocation (or with `register_pr.py --flush`).
  * No secrets in the hook configuration: an optional bearer token is read from $RCP_API_TOKEN.

Manual use
  register_pr.py --flush              retry spooled registrations
  register_pr.py --register <PR URL>  register a PR explicitly
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

API_URL = os.environ.get("RCP_API_URL", "http://localhost:8000").rstrip("/")
SPOOL = Path(os.environ.get("RCP_SPOOL_FILE", Path.home() / ".cache" / "rcp" / "pending-registrations.jsonl"))
PR_CREATE_RE = re.compile(r"(?:^|[\s;&|(])gh\s+pr\s+create\b")
PR_URL_RE = re.compile(r"https://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/pull/(\d+)")


def _gh(args: list[str], cwd: str | None = None) -> dict | None:
    try:
        out = subprocess.run(["gh", *args], cwd=cwd, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        return None


def _response_text(tool_response) -> str:
    if isinstance(tool_response, str):
        return tool_response
    if isinstance(tool_response, dict):
        return "\n".join(str(tool_response.get(k) or "") for k in ("stdout", "stderr", "output", "result"))
    return ""


def resolve_pr(command: str, output: str, cwd: str | None) -> dict | None:
    """Return confirmed PR metadata, or None when no PR was actually created/resolvable."""
    fields = "number,url,headRefName,headRefOid,baseRefName,state,title"
    m = PR_URL_RE.search(output or "")
    target = m.group(0) if m else None
    if target is None:
        # `gh pr create` prints the URL; if output was truncated, ask gh about the current branch.
        info = _gh(["pr", "view", "--json", fields], cwd=cwd)
    else:
        info = _gh(["pr", "view", target, "--json", fields], cwd=cwd)
    if not info or info.get("state") not in ("OPEN", None):
        return None
    url_match = PR_URL_RE.search(info.get("url", ""))
    if not url_match:
        return None
    return {
        "repo": url_match.group(1),
        "pr_number": int(info["number"]),
        "pr_url": info["url"],
        "head_sha": info.get("headRefOid"),
        "head_branch": info.get("headRefName"),
        "source": "hook",
    }


def post(payload: dict) -> tuple[bool, str]:
    req = urllib.request.Request(
        f"{API_URL}/api/tasks/register",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {os.environ['RCP_API_TOKEN']}"} if os.environ.get("RCP_API_TOKEN") else {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = json.loads(resp.read().decode() or "{}")
            verb = "registered" if body.get("created") else "already tracked"
            return True, f"PR #{payload['pr_number']} {verb} as task {body.get('task_id')} → {API_URL}/tasks/{body.get('task_id')}"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:200]
        # 4xx = permanent (bad input, closed PR, not allowed) → do not spool.
        if 400 <= exc.code < 500:
            return True, f"backend rejected registration (HTTP {exc.code}): {detail}"
        return False, f"backend error HTTP {exc.code}: {detail}"
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        return False, f"backend unreachable at {API_URL} ({getattr(exc, 'reason', exc)})"


def spool(payload: dict) -> None:
    SPOOL.parent.mkdir(parents=True, exist_ok=True)
    pending = _read_spool()
    key = (payload["repo"], payload["pr_number"])
    pending = [p for p in pending if (p["repo"], p["pr_number"]) != key] + [payload]
    SPOOL.write_text("".join(json.dumps(p) + "\n" for p in pending))


def _read_spool() -> list[dict]:
    if not SPOOL.exists():
        return []
    out = []
    for line in SPOOL.read_text().splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def flush() -> list[str]:
    pending = _read_spool()
    if not pending:
        return []
    messages, remaining = [], []
    for p in pending:
        ok, msg = post(p)
        (messages if ok else remaining).append(msg if ok else p)
    if remaining:
        SPOOL.write_text("".join(json.dumps(p) + "\n" for p in remaining))
    else:
        SPOOL.unlink(missing_ok=True)
    return messages


def emit(message: str) -> None:
    print(json.dumps({
        "systemMessage": f"[Remediation Control Plane] {message}",
        "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": f"Remediation Control Plane: {message}"},
    }))


def handle_hook(event: dict) -> None:
    if os.environ.get("RCP_AGENT") == "1":
        return  # never register from the control plane's own agent sessions
    if event.get("hook_event_name") not in (None, "PostToolUse") or event.get("tool_name") != "Bash":
        return
    command = str((event.get("tool_input") or {}).get("command") or "")
    if not PR_CREATE_RE.search(command):
        return
    response = event.get("tool_response")
    if isinstance(response, dict) and response.get("interrupted"):
        return
    flushed = flush()
    pr = resolve_pr(command, _response_text(response), event.get("cwd"))
    if pr is None:
        if flushed:
            emit("; ".join(flushed))
        return
    ok, msg = post(pr)
    if not ok:
        spool(pr)
        msg += f" — queued in {SPOOL}; it will be retried automatically (or run `{Path(__file__).name} --flush`)"
    emit("; ".join([*flushed, msg]))


def main(argv: list[str]) -> int:
    try:
        if "--flush" in argv:
            msgs = flush()
            print("\n".join(msgs) or "nothing to flush")
            return 0
        if "--register" in argv:
            url = argv[argv.index("--register") + 1]
            pr = resolve_pr("gh pr create", url, os.getcwd())
            if pr is None:
                print(f"could not resolve open PR {url}", file=sys.stderr)
                return 1
            ok, msg = post(pr)
            if not ok:
                spool(pr)
            print(msg)
            return 0 if ok else 1
        raw = sys.stdin.read()
        handle_hook(json.loads(raw) if raw.strip() else {})
    except Exception as exc:  # the hook must never break the developer's session
        print(json.dumps({"systemMessage": f"[Remediation Control Plane] hook error ignored: {exc}"}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
