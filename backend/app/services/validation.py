"""Local deterministic validation — runs the trusted copy of tools/chart_validator against a worktree."""

from __future__ import annotations

import json
import os
from pathlib import Path

from app.config import get_settings
from app.services import proc


def chart_dirs(worktree: Path, changed_paths: list[str]) -> list[str]:
    """Charts touched by the PR (relative to the worktree), defaulting to every chart under demo/charts."""
    dirs: set[str] = set()
    for p in changed_paths:
        cur = (worktree / p).parent
        while cur != worktree and worktree in cur.parents:
            if (cur / "Chart.yaml").exists():
                dirs.add(str(cur.relative_to(worktree)))
                break
            cur = cur.parent
    if not dirs and (worktree / "demo" / "charts").exists():
        dirs.add("demo/charts")
    return sorted(dirs)


async def validate(worktree: Path, charts: list[str]) -> dict:
    s = get_settings()
    env = {**os.environ, "KUBECONFORM_CACHE": str(s.data_dir / "kubeconform-cache")}
    res = await proc.run(
        [s.validator_python, str(s.validator_script), *charts, "--format", "json"],
        cwd=worktree, timeout=s.validator_timeout_seconds, env=env,
    )
    try:
        report = json.loads(res.stdout)
    except json.JSONDecodeError:
        report = {"valid": False, "charts": [], "error": (res.stderr or res.stdout)[-2000:]}
    report["exit_code"] = res.returncode
    report["tool_error"] = res.returncode == 2 or res.timed_out
    return report


def findings_of(report: dict) -> list[dict]:
    return [f for c in report.get("charts", []) for f in c.get("findings", [])]
