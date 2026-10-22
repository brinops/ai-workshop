#!/usr/bin/env python3
"""Rehearse the Analysis Skill + Remediation Subagent locally, without GitHub or the database.

  uv run --project backend python demo/scripts/agent_dry_run.py C

Creates a throwaway git worktree-like copy of the repo under var/dry-run, injects the scenario,
runs the trusted validator, the real headless Claude Code analysis (same prompt, schema, tools and
permissions as the control plane), reconciles with deterministic findings, runs the real remediation
subagent, then re-validates and prints the diff. Nothing is committed or pushed.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "demo" / "scripts"))

from scenario import apply_edits, load  # noqa: E402

from app.agents import analysis, remediation  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.integrations.claude_runner import AgentSpec, run_agent  # noqa: E402
from app.services import validation  # noqa: E402


def emit(kind: str, text: str) -> None:
    print(f"  [{kind:<11}] {text[:220]}")


async def main(scenario_id: str) -> int:
    s = get_settings()
    sc = load(scenario_id)
    base = s.data_dir / "dry-run" / f"scenario-{sc['id']}"
    wt, bundle = base / "worktree", base / "bundle"
    shutil.rmtree(base, ignore_errors=True)
    (wt / "demo").mkdir(parents=True)
    shutil.copytree(ROOT / "demo" / "charts", wt / "demo" / "charts")
    subprocess.run(["git", "init", "-q"], cwd=wt, check=True)
    subprocess.run(["git", "add", "-A"], cwd=wt, check=True)
    subprocess.run(["git", "-c", "user.name=dry-run", "-c", "user.email=dry@run", "commit", "-qm", "base"], cwd=wt, check=True)
    apply_edits(sc, wt)
    diff = subprocess.run(["git", "diff"], cwd=wt, capture_output=True, text=True).stdout
    subprocess.run(["git", "-c", "user.name=dry-run", "-c", "user.email=dry@run", "commit", "-qam", sc["title"]], cwd=wt, check=True)

    charts = validation.chart_dirs(wt, [sc["file"]])
    report = await validation.validate(wt, charts)
    findings = validation.findings_of(report)
    print(f"== scenario {sc['id']}: local validation → {len(findings)} finding(s)")
    for f in findings:
        print(f"   [{f['category']}] {f['message'][:160]}")

    context = {"pull_request": {"repo": "local/dry-run", "number": 0, "title": sc["title"], "head_sha": "HEAD"},
               "changed_files": [{"filename": sc["file"], "status": "modified"}], "chart_dirs": charts,
               "failed_checks": [{"name": "helm-validate", "conclusion": "failure"}],
               "deterministic_findings": findings, "deterministic_findings_source": "local",
               "remediation_scope": s.remediation_allowed_paths, "worktree": str(wt)}
    ci_log = "\n".join("RCP-FINDING " + json.dumps(f) for f in findings)
    analysis.write_bundle(bundle, context, ci_log, diff, report)

    print("== analysis (headless Claude Code + k8s-failure-analysis skill)")
    res = await run_agent(AgentSpec(
        prompt=analysis.build_prompt(bundle, wt), tools=["Read", "Grep", "Glob", "Skill"],
        allowed_tools=["Read", "Grep", "Glob", "Skill"], json_schema=analysis.output_json_schema(),
        add_dirs=[bundle, wt], timeout=s.analysis_timeout_seconds), emit, asyncio.Event())
    if res.status != "succeeded":
        print(f"analysis {res.status}: {res.error}")
        return 1
    out = analysis.AnalysisOutput.model_validate(res.structured)
    rec = analysis.reconcile(out, findings)
    print(f"   classification={rec.classification} (llm={rec.llm_classification}, det={rec.deterministic_classification}) "
          f"confidence={out.confidence:.2f} remediable={rec.remediable} cost=${res.cost_usd or 0:.3f}")
    print(f"   root cause: {out.root_cause}")
    if not rec.remediable:
        print(f"   → NEEDS_REVIEW: {rec.decision_reason}")
        return 0

    print("== remediation (headless Claude Code --agent k8s-remediator)")
    tools, allowed = remediation.tool_permissions(wt)
    diagnosis = {"classification": rec.classification, "deterministic_findings": findings,
                 "root_cause": out.root_cause, "affected_files": [a.model_dump() for a in out.affected_files],
                 "proposed_fix": out.proposed_fix.model_dump()}
    res = await run_agent(AgentSpec(
        prompt=remediation.build_prompt(diagnosis, wt, bundle, charts), tools=tools, allowed_tools=allowed,
        json_schema=remediation.output_json_schema(), add_dirs=[wt, bundle], agent=remediation.AGENT_NAME,
        timeout=s.remediation_timeout_seconds), emit, asyncio.Event())
    print(f"   agent status={res.status} denials={len(res.permission_denials)} cost=${res.cost_usd or 0:.3f}")
    for d in res.permission_denials:
        print(f"   denied: {json.dumps(d)[:200]}")
    fix_diff = subprocess.run(["git", "diff"], cwd=wt, capture_output=True, text=True).stdout
    report = await validation.validate(wt, charts)
    print("== fix diff\n" + (fix_diff or "(no changes)"))
    print(f"== local validation after fix: {'VALID' if report.get('valid') else 'INVALID'}")
    return 0 if report.get("valid") and fix_diff else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "C")))
