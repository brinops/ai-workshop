#!/usr/bin/env python3
"""Deterministic validator for Helm charts.

Single source of truth for validation: GitHub Actions, the control-plane backend
and the remediation agent all run this exact script.

Stages (per chart):
  1. YAML parsing of Chart.yaml / values*.yaml            -> SYNTAX_ERROR
  2. helm lint --strict                                    -> SYNTAX_ERROR / SCHEMA_VIOLATION
  3. helm template                                         -> SYNTAX_ERROR
  4. kubeconform -strict on rendered manifests             -> SCHEMA_VIOLATION
  5. consistency checks (ports, selectors, probes, env)    -> LOGICAL_CONFIGURATION_ERROR

Output formats:
  text    human readable (default)
  json    one JSON document on stdout
  github  GitHub workflow commands (::error ...) plus `RCP-FINDING {json}` lines that the
          control plane parses from the job log as deterministic evidence.

Exit codes: 0 valid, 1 findings, 2 tool/infrastructure error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

SYNTAX_ERROR = "SYNTAX_ERROR"
SCHEMA_VIOLATION = "SCHEMA_VIOLATION"
LOGICAL_CONFIGURATION_ERROR = "LOGICAL_CONFIGURATION_ERROR"
TOOL_ERROR = "TOOL_ERROR"

WORKLOAD_KINDS = {"Deployment", "StatefulSet", "DaemonSet", "ReplicaSet", "Job"}
SOURCE_RE = re.compile(r"^# Source: (?P<chart>[^/]+)/(?P<path>.+)$", re.MULTILINE)


@dataclass
class Finding:
    category: str
    check: str
    message: str
    chart: str
    file: str | None = None
    line: int | None = None
    resource: str | None = None


@dataclass
class StageResult:
    name: str
    status: str  # passed | failed | skipped | error
    detail: str = ""


@dataclass
class ChartReport:
    chart: str
    stages: list[StageResult] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


def _run(cmd: list[str], stdin: str | None = None, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=timeout)


# ---------------------------------------------------------------- stage 1: YAML
def check_yaml(chart_dir: Path, report: ChartReport) -> bool:
    files = [chart_dir / "Chart.yaml", *sorted(chart_dir.glob("values*.yaml"))]
    ok = True
    for f in files:
        if not f.exists():
            continue
        try:
            list(yaml.safe_load_all(f.read_text()))
        except yaml.MarkedYAMLError as exc:
            ok = False
            mark = exc.problem_mark or exc.context_mark
            line = mark.line + 1 if mark else None
            msg = " ".join(str(p) for p in (exc.context, exc.problem) if p) or str(exc)
            report.findings.append(
                Finding(SYNTAX_ERROR, "yaml-parse", f"Invalid YAML: {msg}", _rel(chart_dir), _rel(f), line)
            )
        except yaml.YAMLError as exc:
            ok = False
            report.findings.append(
                Finding(SYNTAX_ERROR, "yaml-parse", f"Invalid YAML: {exc}", _rel(chart_dir), _rel(f))
            )
    report.stages.append(StageResult("yaml-parse", "passed" if ok else "failed"))
    return ok


# ---------------------------------------------------------------- stage 2: helm lint
LINT_ERROR_RE = re.compile(r"^\[ERROR\]\s*(?P<where>[^:]+):\s*(?P<msg>.+)$", re.MULTILINE)


def check_helm_lint(chart_dir: Path, report: ChartReport) -> bool:
    proc = _run(["helm", "lint", "--strict", str(chart_dir)])
    if proc.returncode == 0:
        report.stages.append(StageResult("helm-lint", "passed"))
        return True
    out = proc.stdout + proc.stderr
    matches = list(LINT_ERROR_RE.finditer(out))
    for m in matches or [None]:
        msg = m.group("msg").strip() if m else out.strip()[-800:]
        where = m.group("where").strip() if m else None
        category = SCHEMA_VIOLATION if "schema" in msg.lower() else SYNTAX_ERROR
        file = _rel(chart_dir / where) if where and (chart_dir / where).exists() else None
        report.findings.append(Finding(category, "helm-lint", msg, _rel(chart_dir), file))
    report.stages.append(StageResult("helm-lint", "failed", out.strip()[-2000:]))
    return False


# ---------------------------------------------------------------- stage 3: helm template
def render(chart_dir: Path, report: ChartReport) -> str | None:
    proc = _run(["helm", "template", "rcp-validate", str(chart_dir)])
    if proc.returncode != 0:
        msg = proc.stderr.strip() or proc.stdout.strip()
        report.findings.append(Finding(SYNTAX_ERROR, "helm-template", msg[-1500:], _rel(chart_dir)))
        report.stages.append(StageResult("helm-template", "failed", msg[-2000:]))
        return None
    report.stages.append(StageResult("helm-template", "passed"))
    return proc.stdout


def split_rendered(chart_dir: Path, rendered: str) -> list[tuple[str | None, dict]]:
    """Return (source template path, document) pairs from `helm template` output."""
    docs: list[tuple[str | None, dict]] = []
    for chunk in re.split(r"^---\s*$", rendered, flags=re.MULTILINE):
        if not chunk.strip():
            continue
        m = SOURCE_RE.search(chunk)
        source = _rel(chart_dir / m.group("path")) if m else None
        try:
            doc = yaml.safe_load(chunk)
        except yaml.YAMLError:
            continue
        if isinstance(doc, dict):
            docs.append((source, doc))
    return docs


def _resource_id(doc: dict) -> str:
    return f"{doc.get('kind', '?')}/{(doc.get('metadata') or {}).get('name', '?')}"


# ---------------------------------------------------------------- stage 4: kubeconform
def check_kubeconform(chart_dir: Path, rendered: str, report: ChartReport) -> bool:
    cmd = ["kubeconform", "-strict", "-summary", "-output", "json"]
    if cache := os.environ.get("KUBECONFORM_CACHE"):
        Path(cache).mkdir(parents=True, exist_ok=True)
        cmd += ["-cache", cache]
    if k8s := os.environ.get("KUBERNETES_VERSION"):
        cmd += ["-kubernetes-version", k8s]
    proc = _run(cmd, stdin=rendered)
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        report.findings.append(Finding(TOOL_ERROR, "kubeconform", proc.stderr.strip()[-800:], _rel(chart_dir)))
        report.stages.append(StageResult("kubeconform", "error", proc.stderr.strip()[-2000:]))
        return False

    sources = {_resource_id(d): s for s, d in split_rendered(chart_dir, rendered)}
    ok = True
    for res in payload.get("resources", []):
        status = res.get("status")
        if status in ("statusValid", "statusSkipped"):
            continue
        rid = f"{res.get('kind')}/{res.get('name')}"
        if status == "statusError":
            ok = False
            report.findings.append(
                Finding(TOOL_ERROR, "kubeconform", res.get("msg", "kubeconform error"), _rel(chart_dir), sources.get(rid), resource=rid)
            )
            continue
        ok = False
        errors = res.get("validationErrors") or [{"path": "", "msg": res.get("msg", "invalid")}]
        for err in errors:
            report.findings.append(
                Finding(
                    SCHEMA_VIOLATION,
                    "kubeconform",
                    f"{err.get('path') or '/'}: {err.get('msg')}",
                    _rel(chart_dir),
                    sources.get(rid),
                    resource=rid,
                )
            )
    tool_error = any(f.category == TOOL_ERROR for f in report.findings)
    report.stages.append(StageResult("kubeconform", "error" if tool_error else ("passed" if ok else "failed")))
    return ok


# ---------------------------------------------------------------- stage 5: consistency
def _pod_spec(doc: dict) -> dict | None:
    spec = doc.get("spec") or {}
    if doc.get("kind") == "Job":
        return ((spec.get("template") or {}).get("spec")) or None
    return ((spec.get("template") or {}).get("spec")) or None


def _pod_labels(doc: dict) -> dict:
    return (((doc.get("spec") or {}).get("template") or {}).get("metadata") or {}).get("labels") or {}


def check_consistency(chart_dir: Path, rendered: str, report: ChartReport) -> bool:
    docs = split_rendered(chart_dir, rendered)
    workloads = [(s, d) for s, d in docs if d.get("kind") in WORKLOAD_KINDS and _pod_spec(d)]
    findings: list[Finding] = []
    chart = _rel(chart_dir)

    for source, wl in workloads:
        for c in _pod_spec(wl).get("containers") or []:
            ports = c.get("ports") or []
            numbers = {p.get("containerPort") for p in ports}
            names = {p.get("name") for p in ports if p.get("name")}
            cname = f"{_resource_id(wl)} container '{c.get('name')}'"
            for probe_name in ("readinessProbe", "livenessProbe", "startupProbe"):
                probe = c.get(probe_name) or {}
                handler = probe.get("httpGet") or probe.get("tcpSocket") or {}
                port = handler.get("port")
                if port is None:
                    continue
                if (isinstance(port, int) and port not in numbers) or (isinstance(port, str) and port not in names):
                    findings.append(
                        Finding(
                            LOGICAL_CONFIGURATION_ERROR,
                            "probe-port",
                            f"{cname}: {probe_name} targets port {port!r}, which is not a declared container port "
                            f"(declared: {sorted(numbers)} / names {sorted(names)})",
                            chart, source, resource=_resource_id(wl),
                        )
                    )
            env_port = next((e.get("value") for e in c.get("env") or [] if e.get("name") == "PORT"), None)
            if env_port is not None and str(env_port).isdigit() and numbers and int(env_port) not in numbers:
                findings.append(
                    Finding(
                        LOGICAL_CONFIGURATION_ERROR,
                        "env-port",
                        f"{cname}: application listens on PORT={env_port} but declares containerPort {sorted(numbers)}",
                        chart, source, resource=_resource_id(wl),
                    )
                )

    for source, svc in docs:
        if svc.get("kind") != "Service":
            continue
        spec = svc.get("spec") or {}
        selector = spec.get("selector") or {}
        if not selector:
            continue
        matched = [
            (s, w) for s, w in workloads if all(_pod_labels(w).get(k) == v for k, v in selector.items())
        ]
        if not matched:
            findings.append(
                Finding(
                    LOGICAL_CONFIGURATION_ERROR,
                    "service-selector",
                    f"{_resource_id(svc)} selector {selector} matches no workload pod template in this chart",
                    chart, source, resource=_resource_id(svc),
                )
            )
            continue
        numbers: set = set()
        names: set = set()
        for _, w in matched:
            for c in _pod_spec(w).get("containers") or []:
                for p in c.get("ports") or []:
                    numbers.add(p.get("containerPort"))
                    if p.get("name"):
                        names.add(p.get("name"))
        for port in spec.get("ports") or []:
            target = port.get("targetPort", port.get("port"))
            if (isinstance(target, int) and target not in numbers) or (isinstance(target, str) and target not in names):
                backends = ", ".join(_resource_id(w) for _, w in matched)
                findings.append(
                    Finding(
                        LOGICAL_CONFIGURATION_ERROR,
                        "service-target-port",
                        f"{_resource_id(svc)} port '{port.get('name', port.get('port'))}' targetPort {target!r} does not "
                        f"match any container port of {backends} (container ports: {sorted(numbers)}, "
                        f"names: {sorted(names)}) — traffic would be dropped",
                        chart, source, resource=_resource_id(svc),
                    )
                )

    report.findings.extend(findings)
    report.stages.append(StageResult("consistency", "failed" if findings else "passed"))
    return not findings


# ---------------------------------------------------------------- driver
def validate_chart(chart_dir: Path) -> ChartReport:
    report = ChartReport(chart=_rel(chart_dir))
    skipped = ["helm-lint", "helm-template", "kubeconform", "consistency"]
    if not check_yaml(chart_dir, report):
        report.stages += [StageResult(s, "skipped", "blocked by YAML errors") for s in skipped]
        return report
    lint_ok = check_helm_lint(chart_dir, report)
    rendered = render(chart_dir, report)
    if rendered is None:
        report.stages += [StageResult(s, "skipped", "rendering failed") for s in skipped[2:]]
        return report
    if not lint_ok and any(f.check == "helm-lint" and f.category == SYNTAX_ERROR for f in report.findings):
        report.stages += [StageResult(s, "skipped", "blocked by lint errors") for s in skipped[2:]]
        return report
    check_kubeconform(chart_dir, rendered, report)
    check_consistency(chart_dir, rendered, report)
    return report


def discover(paths: list[str]) -> list[Path]:
    charts: list[Path] = []
    for p in paths:
        base = Path(p)
        if (base / "Chart.yaml").exists():
            charts.append(base)
            continue
        charts.extend(sorted(c.parent for c in base.rglob("Chart.yaml")))
    seen: set[Path] = set()
    unique = []
    for c in charts:
        if c.resolve() not in seen:
            seen.add(c.resolve())
            unique.append(c)
    return unique


def _gh_escape(s: str) -> str:
    return s.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", default=["demo/charts"], help="chart directories or roots to search")
    ap.add_argument("--format", choices=["text", "json", "github"], default="text")
    args = ap.parse_args(argv)

    missing = [b for b in ("helm", "kubeconform") if not shutil.which(b)]
    if missing:
        print(f"missing required binaries: {', '.join(missing)}", file=sys.stderr)
        return 2

    charts = discover(args.paths)
    if not charts:
        print("no charts found", file=sys.stderr)
        return 2
    reports = [validate_chart(c) for c in charts]
    findings = [f for r in reports for f in r.findings]
    tool_errors = [f for f in findings if f.category == TOOL_ERROR]

    if args.format == "json":
        print(json.dumps({
            "valid": not findings,
            "charts": [
                {"chart": r.chart, "stages": [asdict(s) for s in r.stages], "findings": [asdict(f) for f in r.findings]}
                for r in reports
            ],
        }, indent=2))
    elif args.format == "github":
        for r in reports:
            print(f"::group::{r.chart}")
            for s in r.stages:
                print(f"  {s.name:<14} {s.status}")
            print("::endgroup::")
        for f in findings:
            props = [f"title={f.category} ({f.check})"]
            if f.file:
                props.insert(0, f"file={f.file}")
                if f.line:
                    props.insert(1, f"line={f.line}")
            print(f"::error {','.join(props)}::{_gh_escape(f.message)}")
            print("RCP-FINDING " + json.dumps(asdict(f), sort_keys=True))
        print(f"{len(charts)} chart(s) validated, {len(findings)} finding(s)")
    else:
        for r in reports:
            print(f"== {r.chart}")
            for s in r.stages:
                print(f"   {s.name:<14} {s.status}")
            for f in r.findings:
                loc = f"{f.file}:{f.line}" if f.line else (f.file or r.chart)
                print(f"   [{f.category}] {f.check} {loc}: {f.message}")
        print("VALID" if not findings else f"INVALID ({len(findings)} finding(s))")

    if tool_errors and len(tool_errors) == len(findings):
        return 2
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
