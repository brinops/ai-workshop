"""Demo scenarios and the deterministic validator, using the real helm + kubeconform binaries."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "demo" / "scripts"))
sys.path.insert(0, str(ROOT / ".claude" / "skills" / "k8s-failure-analysis" / "scripts"))

import scenario  # noqa: E402
import validate  # noqa: E402

pytestmark = pytest.mark.skipif(not (shutil.which("helm") and shutil.which("kubeconform")),
                                reason="helm and kubeconform are required")


@pytest.fixture(autouse=True)
def kubeconform_cache(monkeypatch):
    cache = ROOT / "var" / "kubeconform-cache"
    monkeypatch.setenv("KUBECONFORM_CACHE", str(cache))


def test_baseline_chart_is_valid():
    rep = validate.validate_chart(ROOT / "demo" / "charts" / "payments-api")
    assert rep.findings == [], rep.findings
    assert [s.status for s in rep.stages] == ["passed"] * 5


@pytest.mark.parametrize("sid", ["A", "B", "C"])
def test_scenario_fails_for_intended_reason_only(sid):
    ok, details = scenario.verify(scenario.load(sid))
    assert ok, details


def test_consistency_check_catches_probe_and_selector(tmp_path):
    chart = tmp_path / "demo" / "charts" / "payments-api"
    shutil.copytree(ROOT / "demo" / "charts" / "payments-api", chart)
    svc = chart / "templates" / "service.yaml"
    svc.write_text(svc.read_text().replace('{{- include "payments-api.selectorLabels" . | nindent 4 }}',
                                           "app: something-else"))
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        rep = validate.validate_chart(Path("demo/charts/payments-api"))
    finally:
        os.chdir(cwd)
    assert {f.check for f in rep.findings} == {"service-selector"}
    assert all(f.category == validate.LOGICAL_CONFIGURATION_ERROR for f in rep.findings)


def test_scenario_edits_refuse_already_modified_chart(tmp_path):
    sc = scenario.load("C")
    target = tmp_path / sc["file"]
    target.parent.mkdir(parents=True)
    target.write_text("service:\n  targetPort: 1234\n")
    with pytest.raises(SystemExit):
        scenario.apply_edits(sc, tmp_path)
