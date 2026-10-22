#!/usr/bin/env python3
"""Reproducible workshop failure scenarios.

  scenario.py list
  scenario.py verify  <A|B|C|all>   prove the scenario fails for the intended reason (temp copy, no git changes)
  scenario.py prepare <A|B|C> [--base main] [--no-push]
                                    new branch from origin/<base> (in a throwaway worktree), inject the error,
                                    verify, commit, push, and print the `gh pr create` command to run from
                                    Claude Code

The scenario never weakens validation: `verify` asserts that the *real* validator reports
the expected category and nothing else.
"""

from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = ROOT / "demo" / "scenarios"
VALIDATOR = ROOT / "tools" / "chart_validator" / "validate.py"


def load(scenario_id: str) -> dict:
    for f in sorted(SCENARIOS.glob("*.yaml")):
        data = yaml.safe_load(f.read_text())
        if data["id"].upper() == scenario_id.upper():
            return data
    raise SystemExit(f"unknown scenario {scenario_id!r}; run `scenario.py list`")


def all_scenarios() -> list[dict]:
    return [yaml.safe_load(f.read_text()) for f in sorted(SCENARIOS.glob("*.yaml"))]


def apply_edits(scenario: dict, root: Path) -> Path:
    target = root / scenario["file"]
    text = target.read_text()
    for edit in scenario["edits"]:
        if edit["old"] not in text:
            raise SystemExit(f"scenario {scenario['id']}: expected text not found in {scenario['file']} — is the chart already modified?")
        text = text.replace(edit["old"], edit["new"], 1)
    target.write_text(text)
    return target


def run_validator(root: Path, chart_dir: str) -> dict:
    proc = subprocess.run(
        [sys.executable, str(VALIDATOR), chart_dir, "--format", "json"],
        cwd=root, capture_output=True, text=True, timeout=300,
    )
    if proc.returncode == 2:
        raise SystemExit(f"validator tool error:\n{proc.stderr}{proc.stdout}")
    return json.loads(proc.stdout)


def verify(scenario: dict) -> tuple[bool, str]:
    chart_dir = str(Path(scenario["file"]).parent)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        shutil.copytree(ROOT / chart_dir, tmp_root / chart_dir)
        baseline = run_validator(tmp_root, chart_dir)
        if not baseline["valid"]:
            return False, "baseline chart is already invalid — reset the chart before running scenarios"
        apply_edits(scenario, tmp_root)
        report = run_validator(tmp_root, chart_dir)
    findings = [f for c in report["charts"] for f in c["findings"]]
    categories = {f["category"] for f in findings}
    expected = scenario["expected_category"]
    lines = [f"  [{f['category']}] {f['check']}: {f['message'][:160]}" for f in findings]
    ok = categories == {expected}
    return ok, "\n".join(lines) or "  (no findings)"


def git(*args: str, cwd: Path = ROOT, check: bool = True) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed:\n{proc.stderr}")
    return proc.stdout.strip()


def prepare(scenario: dict, base: str, push: bool) -> None:
    """Create the scenario branch in a separate worktree — the operator's checkout is never touched."""
    ok, details = verify(scenario)
    if not ok:
        raise SystemExit(f"scenario {scenario['id']} does not fail for the intended reason:\n{details}")

    git("fetch", "origin", base)
    branch = f"demo/{scenario['slug']}-{datetime.now():%Y%m%d-%H%M%S}"
    wt = ROOT / "var" / "scenarios" / branch.replace("/", "_")
    git("worktree", "add", "-b", branch, str(wt), f"origin/{base}")
    try:
        apply_edits(scenario, wt)
        git("add", scenario["file"], cwd=wt)
        git("commit", "-m", scenario["title"], "-m", scenario["pr_body"].strip(), cwd=wt)
        if push:
            git("push", "-u", "origin", branch, cwd=wt)
    finally:
        git("worktree", "remove", "--force", str(wt), check=False)

    body = scenario["pr_body"].strip()
    print(f"\nScenario {scenario['id']} ({scenario['expected_category']}) pushed to branch {branch}")
    print("Validator findings (expected failure):")
    print(details)
    print("\nNow open the PR from Claude Code so the PostToolUse hook registers it:\n")
    print(f"  gh pr create --base {shlex.quote(base)} --head {shlex.quote(branch)} "
          f"--title {shlex.quote(scenario['title'])} --body {shlex.quote(body)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    v = sub.add_parser("verify")
    v.add_argument("scenario")
    p = sub.add_parser("prepare")
    p.add_argument("scenario")
    p.add_argument("--base", default="main")
    p.add_argument("--no-push", action="store_true")
    args = ap.parse_args()

    if args.cmd == "list":
        for s in all_scenarios():
            print(f"{s['id']}  {s['expected_category']:<28} {s['title']}")
        return 0
    if args.cmd == "verify":
        targets = all_scenarios() if args.scenario.lower() == "all" else [load(args.scenario)]
        failed = 0
        for s in targets:
            ok, details = verify(s)
            print(f"{'PASS' if ok else 'FAIL'}  scenario {s['id']} -> expected {s['expected_category']}\n{details}")
            failed += not ok
        return 1 if failed else 0
    prepare(load(args.scenario), args.base, push=not args.no_push)
    return 0


if __name__ == "__main__":
    sys.exit(main())
