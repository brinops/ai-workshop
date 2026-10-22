#!/usr/bin/env python3
"""Workshop preflight: verifies binaries, credentials, integrations and service health.

  python3 scripts/preflight.py            fast checks (no spend, no messages)
  python3 scripts/preflight.py --live     also runs a tiny headless Claude Code call (costs < $0.01)
  python3 scripts/preflight.py --slack    also posts a test message to the Slack webhook

Exit code 0 when every required check passes.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OK, WARN, FAIL = "\033[32m✓\033[0m", "\033[33m!\033[0m", "\033[31m✗\033[0m"
results: list[tuple[str, str, str, bool]] = []  # (mark, name, detail, required)


def load_env() -> dict[str, str]:
    env = dict(os.environ)
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text().splitlines():
            m = re.match(r"^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$", line)
            if m and m.group(1) not in os.environ:
                env[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return env


def sh(*cmd: str, timeout: int = 30, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd or ROOT)


def check(name: str, ok: bool, detail: str, required: bool = True) -> bool:
    results.append((OK if ok else (FAIL if required else WARN), name, detail, required))
    return ok


def repo_from_remote() -> str | None:
    out = sh("git", "remote", "get-url", "origin").stdout.strip()
    m = re.search(r"github\.com[:/]([^/]+/[^/.]+)", out)
    return m.group(1) if m else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="run a real headless Claude Code call")
    ap.add_argument("--slack", action="store_true", help="send a Slack test message")
    args = ap.parse_args()
    env = load_env()

    # --- binaries
    for b, required in [("just", True), ("git", True), ("gh", True), ("claude", True), ("helm", True), ("kubeconform", True),
                        ("uv", True), ("pnpm", False), ("docker", False)]:
        path = shutil.which(b)
        check(f"binary: {b}", bool(path), path or "not found on PATH", required)

    # --- GitHub
    repo = env.get("RCP_REPO") or repo_from_remote()
    auth = sh("gh", "auth", "status")
    check("GitHub CLI auth", auth.returncode == 0, (auth.stdout + auth.stderr).strip().splitlines()[1].strip()
          if auth.returncode == 0 else "run `gh auth login`")
    if repo:
        view = sh("gh", "repo", "view", repo, "--json", "viewerPermission,defaultBranchRef")
        if view.returncode == 0:
            info = json.loads(view.stdout)
            perm, default = info["viewerPermission"], (info.get("defaultBranchRef") or {}).get("name")
            check("GitHub repository", perm in ("ADMIN", "MAINTAIN", "WRITE"), f"{repo} · permission {perm} · default {default}")
            wf = sh("gh", "api", f"repos/{repo}/contents/.github/workflows/helm-validate.yaml")
            check("helm-validate workflow on default branch", wf.returncode == 0,
                  "present" if wf.returncode == 0 else "missing — merge the control-plane PR first")
        else:
            check("GitHub repository", False, view.stderr.strip()[:120])
    else:
        check("GitHub repository", False, "set RCP_REPO or an origin remote")
    push = sh("git", "ls-remote", "--heads", "origin", timeout=30)
    check("git remote access (push credentials)", push.returncode == 0, "origin reachable" if push.returncode == 0
          else push.stderr.strip()[:120])

    # --- Claude Code
    ver = sh("claude", "--version") if shutil.which("claude") else None
    check("Claude Code version", bool(ver and ver.returncode == 0), (ver.stdout.strip() if ver else "missing"))
    if args.live and ver:
        r = sh("claude", "-p", "Reply with the single word OK", "--model", "haiku", "--output-format", "json",
               "--tools", "", "--max-budget-usd", "0.05", "--no-session-persistence", timeout=120)
        ok = r.returncode == 0 and '"is_error":false' in r.stdout.replace(" ", "")
        check("Claude Code headless auth (live)", ok, "headless call succeeded" if ok else (r.stderr or r.stdout)[-200:])
    else:
        check("Claude Code headless auth", True, "skipped (use --live)", required=False)

    # --- control-plane.yaml (repositories, routes; every skill/agent/validator must exist)
    py_bin = ROOT / "backend" / ".venv" / "bin" / "python"
    if py_bin.exists():
        r = sh(str(py_bin), "-c", "from app.control_plane import load; c = load(); "
               "print('; '.join(f'{x.repo}: ' + ', '.join(f'{r.check} → {r.remediation_agent}' for r in x.routes) "
               "for x in c.repositories))", cwd=ROOT / "backend")
        check("control-plane.yaml", r.returncode == 0, (r.stdout.strip() or r.stderr.strip().splitlines()[-1])[:160])
        if repo and r.returncode == 0:
            check("repository is configured", repo.lower() in r.stdout.lower(), repo)

    # --- validator + scenarios
    py = ROOT / "backend" / ".venv" / "bin" / "python"
    if py.exists():
        r = sh(str(py), "demo/scripts/scenario.py", "verify", "all", timeout=300)
        check("demo scenarios fail for the intended reason", r.returncode == 0,
              " · ".join(ln for ln in r.stdout.splitlines() if ln.startswith(("PASS", "FAIL"))) or r.stderr[-200:])
    else:
        check("backend virtualenv", False, "run `just install`")

    # --- Slack
    hook = env.get("SLACK_WEBHOOK_URL")
    check("Slack webhook configured", bool(hook), "SLACK_WEBHOOK_URL set" if hook else "set SLACK_WEBHOOK_URL in .env")
    if args.slack and hook:
        req = urllib.request.Request(hook, data=json.dumps({"text": ":wave: Remediation Control Plane preflight"}).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                check("Slack test message", resp.status == 200, "delivered")
        except urllib.error.URLError as exc:
            check("Slack test message", False, str(exc)[:120])

    # --- service
    api = (env.get("RCP_API_URL") or env.get("PUBLIC_URL") or "http://127.0.0.1:8000").rstrip("/")
    try:
        with urllib.request.urlopen(f"{api}/api/health", timeout=5) as resp:
            health = json.loads(resp.read())
        check("control plane API", True, api)
        for name, comp in health["components"].items():
            check(f"  health: {name}", comp["ok"], comp["detail"], required=name in ("database", "worker", "github", "claude"))
        check("dashboard build", (ROOT / "frontend" / "dist" / "index.html").exists(),
              "frontend/dist present" if (ROOT / "frontend" / "dist" / "index.html").exists() else "run `just build-ui`",
              required=False)
    except (urllib.error.URLError, OSError) as exc:
        check("control plane API", False, f"{api} unreachable ({exc}) — run `just dev`")

    width = max(len(r[1]) for r in results)
    for mark, name, detail, _ in results:
        print(f" {mark} {name:<{width}}  {detail}")
    failed = [r for r in results if r[0] == FAIL]
    print(f"\n{'READY' if not failed else f'{len(failed)} required check(s) failed'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
