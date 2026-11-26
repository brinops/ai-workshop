import asyncio
import json
import subprocess
import sys

import pytest

from app.config import REPO_ROOT
from app.integrations.claude_runner import AgentResult
from app.orchestration.booking_repair import (
    FIXTURE,
    PAGE_CHECK_PASSED,
    PAGE_REVIEW_COMMAND,
    PAGE_RUNBOOK,
    PAGE_SCRIPT,
    PAGE_SKILL_PERMISSION,
    BookingPlan,
    SelectedRoute,
    candidate_source,
    repair_booking,
)

FIX = """await self._check_eligibility(user_id)
if self.remaining_seats > 0:
    self.remaining_seats -= 1
    self.confirmed.append(user_id)
    return "confirmed"
self.waitlist.append(user_id)
return "waitlisted"
"""


@pytest.mark.parametrize(("verdict", "status"), [("approved", "passed"), ("changes_required", "failed")])
async def test_agent_patch_runs_real_booking_tests_before_qa(verdict, status):
    original = REPO_ROOT / FIXTURE / "service.py"
    source = original.read_text(encoding="utf-8")

    plan = BookingPlan(
        goal="Fix race", steps=["Move capacity check"], acceptance_criteria=["Only one confirmation"],
        route=SelectedRoute(id="booking-backend", execution_agent="workshop-booking-backend", qa_agent="workshop-booking-qa"),
    )

    async def agent(spec, *_):
        assert spec.tools == ["StructuredOutput"]
        assert spec.cwd != REPO_ROOT
        payload = json.loads(spec.prompt)
        assert payload["plan"] == plan.model_dump()
        if spec.agent == plan.route.qa_agent:
            assert "2 passed" in payload["test_output"]
            return AgentResult(status="succeeded", structured={"verdict": verdict, "summary": "Reviewed criteria."})
        assert spec.agent == plan.route.execution_agent
        return AgentResult(status="succeeded", structured={"body": FIX, "summary": "Read capacity after awaiting."})

    result = await repair_booking("Approved booking report", plan, agent, asyncio.Event(), 10)
    assert result["status"] == status and result["qa"]["verdict"] == verdict
    assert "2 passed" in result["test_output"]
    assert "+        if self.remaining_seats > 0:" in result["patch"]
    assert original.read_text(encoding="utf-8") == source


def test_agent_patch_rejects_unrelated_code():
    source = (REPO_ROOT / FIXTURE / "service.py").read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="supported Python subset"):
        candidate_source(source, "import os\nreturn 'confirmed'")


@pytest.mark.parametrize("mode", ["approved", "skip_script", "invalid_page"])
async def test_static_page_requires_backend_checks_and_reviewer_skill(mode):
    plan = BookingPlan(
        goal="Create a page", steps=["Add markup and styles"], acceptance_criteria=["Link to waitlist"],
        route=SelectedRoute(id="static-page", execution_agent="workshop-developer",
                            qa_agent="workshop-reviewer", implementation="static-page"),
    )
    calls = []

    async def agent(spec, emit, *_):
        calls.append(spec.agent)
        if spec.agent == "workshop-developer":
            html = """<!doctype html><html><title>Booking</title>
                <link rel="stylesheet" href="styles.css"><main>
                <h1>Booking</h1><a href="#waitlist">Waitlist</a>
                <section id="waitlist">Join the waitlist.</section></main></html>"""
            return AgentResult(status="succeeded", structured={
                "index_html": html if mode != "invalid_page" else "<h1>Booking</h1>",
                "styles_css": "main { max-width: 50rem; }",
                "summary": "Create a booking page.",
            })
        assert spec.tools == ["StructuredOutput", "Skill", "Read", "Bash"]
        assert spec.allowed_tools == ["StructuredOutput", PAGE_SKILL_PERMISSION, f"Read(./{PAGE_RUNBOOK.as_posix()})",
                                      f"Bash({PAGE_REVIEW_COMMAND})"]
        assert PAGE_REVIEW_COMMAND in (spec.cwd / PAGE_RUNBOOK).read_text()
        assert (spec.cwd / PAGE_SCRIPT.parent.parent / "SKILL.md").is_file()
        assert PAGE_CHECK_PASSED in json.loads(spec.prompt)["test_output"]
        if mode != "skip_script":
            check = subprocess.run(
                [sys.executable, "-I", str(PAGE_SCRIPT)], cwd=spec.cwd, capture_output=True, text=True, check=True,
            )
            emit("tool_use", f"Bash · {PAGE_REVIEW_COMMAND}")
            emit("tool_result", check.stdout.strip())
        return AgentResult(status="succeeded", structured={"verdict": "approved", "summary": "Matches the plan."})

    result = await repair_booking("Create an offline HTML page", plan, agent, asyncio.Event(), 10)
    assert result["status"] == ("passed" if mode == "approved" else "failed")
    assert "+++ b/demo/static-page/index.html" in result["patch"]
    assert "+++ b/demo/static-page/styles.css" in result["patch"]
    assert result["tests_passed"] == (mode != "invalid_page")
    assert result.get("review_script_checked") == {"approved": True, "skip_script": False, "invalid_page": None}[mode]
    assert calls == (["workshop-developer"] if mode == "invalid_page" else ["workshop-developer", "workshop-reviewer"])
