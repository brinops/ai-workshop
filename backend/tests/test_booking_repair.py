import asyncio

import pytest

from app.config import REPO_ROOT
from app.integrations.claude_runner import AgentResult
from app.orchestration.booking_repair import FIXTURE, candidate_source, repair_booking

FIX = """await self._check_eligibility(user_id)
if self.remaining_seats > 0:
    self.remaining_seats -= 1
    self.confirmed.append(user_id)
    return "confirmed"
self.waitlist.append(user_id)
return "waitlisted"
"""


async def test_agent_patch_runs_real_booking_tests_on_copy():
    original = REPO_ROOT / FIXTURE / "service.py"
    source = original.read_text(encoding="utf-8")

    async def agent(spec, *_):
        assert spec.tools == ["StructuredOutput"]
        assert spec.cwd != REPO_ROOT
        return AgentResult(status="succeeded", structured={"body": FIX, "summary": "Read capacity after awaiting."})

    result = await repair_booking("Approved booking report", agent, asyncio.Event(), 10)
    assert result["status"] == "passed"
    assert "2 passed" in result["test_output"]
    assert "+        if self.remaining_seats > 0:" in result["patch"]
    assert original.read_text(encoding="utf-8") == source


def test_agent_patch_rejects_unrelated_code():
    source = (REPO_ROOT / FIXTURE / "service.py").read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="supported Python subset"):
        candidate_source(source, "import os\nreturn 'confirmed'")
