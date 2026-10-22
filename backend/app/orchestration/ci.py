"""Aggregation of GitHub check runs into one verdict for the required checks of one commit."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import StrEnum

from app.integrations.github import CheckRun


class CIOverall(StrEnum):
    PENDING = "pending"  # not all required checks have completed (or not reported yet)
    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"  # a required check was skipped/neutral — not proof of validity


FAILED_CONCLUSIONS = {"failure", "timed_out", "action_required", "startup_failure"}
SKIPPED_CONCLUSIONS = {"skipped", "neutral"}


@dataclass
class CIResult:
    overall: CIOverall
    required: list[dict] = field(default_factory=list)  # one entry per required check name
    others: list[dict] = field(default_factory=list)

    @property
    def failed_runs(self) -> list[dict]:
        return [c for c in self.required if c["verdict"] == "failure"]


def verdict(run: CheckRun | None) -> str:
    if run is None:
        return "missing"
    if run.status != "completed":
        return "pending"
    c = run.conclusion or ""
    if c == "success":
        return "success"
    if c in FAILED_CONCLUSIONS:
        return "failure"
    if c == "cancelled":
        return "cancelled"
    if c in SKIPPED_CONCLUSIONS:
        return "skipped"
    return "pending"  # stale / unknown


def aggregate(runs: list[CheckRun], required_names: list[str]) -> CIResult:
    latest: dict[str, CheckRun] = {}
    for r in runs:
        if r.name not in latest or r.id > latest[r.name].id:
            latest[r.name] = r
    names = required_names or sorted(latest)
    required = [{**(latest[n].as_dict() if n in latest else {"name": n}), "verdict": verdict(latest.get(n))} for n in names]
    others = [{**r.as_dict(), "verdict": verdict(r)} for n, r in sorted(latest.items()) if n not in names]
    verdicts = {c["verdict"] for c in required}

    if not required:
        overall = CIOverall.PENDING
    elif "failure" in verdicts:
        overall = CIOverall.FAILURE
    elif "cancelled" in verdicts:
        overall = CIOverall.CANCELLED
    elif verdicts & {"pending", "missing"}:
        overall = CIOverall.PENDING
    elif "skipped" in verdicts:
        overall = CIOverall.SKIPPED
    else:
        overall = CIOverall.SUCCESS
    return CIResult(overall, required, others)


# ------------------------------------------------------------------ log evidence
_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T[\d:.]+Z ?")
FINDING_RE = re.compile(r"RCP-FINDING (\{.*\})\s*$")


def strip_timestamps(log: str) -> str:
    return "\n".join(_TS.sub("", line) for line in log.splitlines())


def extract_findings(log: str) -> list[dict]:
    """Deterministic validator findings emitted in the CI log (`RCP-FINDING {json}`)."""
    out: list[dict] = []
    for line in strip_timestamps(log).splitlines():
        m = FINDING_RE.search(line)
        if not m:
            continue
        try:
            f = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(f, dict) and "category" in f and f not in out:
            out.append(f)
    return out


def log_excerpt(log: str, max_lines: int = 160) -> str:
    """Keep the error-bearing tail of a job log, without runner timestamps."""
    lines = strip_timestamps(log).splitlines()
    error_idx = [i for i, ln in enumerate(lines) if "##[error]" in ln or "::error" in ln or "RCP-FINDING" in ln]
    if error_idx:
        start = max(0, error_idx[0] - 60)
        lines = lines[start:error_idx[-1] + 20]
    return "\n".join(lines[-max_lines:])
