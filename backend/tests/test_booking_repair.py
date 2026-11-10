import asyncio
import json

import pytest

from app.config import REPO_ROOT
from app.integrations.claude_runner import AgentResult
from app.orchestration.booking_repair import FIXTURE, BookingPlan, SelectedRoute, candidate_source, repair_booking

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
