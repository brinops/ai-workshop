"""Local deterministic validation — runs the route's trusted validator (from the control plane) on a worktree."""

from __future__ import annotations

import json
import os
from pathlib import Path

from app.config import get_settings
from app.control_plane import Route
from app.services import proc


async def validate(worktree: Path, route: Route) -> dict:
    """Run the route's validator on its scan roots inside the worktree. Contract: `--format json` report."""
    s = get_settings()
    env = {**os.environ, "KUBECONFORM_CACHE": str(s.data_dir / "kubeconform-cache")}
    res = await proc.run(
        [s.validator_python, str(route.validator_path), *route.scan_roots, "--format", "json"],
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
    """Findings from a validator report; `charts` (Helm) and the generic `targets` key are both accepted."""
    groups = report.get("charts") or report.get("targets") or []
    return [f for g in groups for f in g.get("findings", [])]
