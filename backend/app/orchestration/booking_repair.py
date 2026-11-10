"""Prepare and verify an agent patch for the workshop booking fixture."""

import ast
import asyncio
import difflib
import json
import shutil
import sys
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from textwrap import indent
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.config import REPO_ROOT
from app.control_plane import AgentName, get_config
from app.db import session_scope, utcnow
from app.integrations.claude_runner import AgentSpec
from app.models.jira_workflow import (
    JiraWorkflowDecision,
    JiraWorkflowDraft,
    JiraWorkflowEvent,
    JiraWorkflowOperation,
    JiraWorkflowRun,
    JiraWorkflowState,
)
from app.services.redaction import redact

KIND = "booking_repair"
FIXTURE = Path("demo/booking")
SCHEMA = {
    "type": "object",
    "properties": {"body": {"type": "string"}, "summary": {"type": "string"}},
    "required": ["body", "summary"],
    "additionalProperties": False,
}
PlanText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class PlanContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: PlanText
    steps: list[PlanText] = Field(min_length=1, max_length=5)
    acceptance_criteria: list[PlanText] = Field(min_length=1, max_length=5)


class RouteSelection(PlanContent):
    route: AgentName | None


class SelectedRoute(BaseModel):
    id: AgentName
    execution_agent: AgentName
    qa_agent: AgentName


class BookingPlan(PlanContent):
    route: SelectedRoute | None = None


class BookingQA(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Literal["approved", "changes_required"]
    summary: PlanText


ALLOWED_NODES = (
    ast.Module, ast.AsyncFunctionDef, ast.arguments, ast.arg, ast.Expr, ast.Await, ast.Call, ast.Attribute,
    ast.Name, ast.Load, ast.Store, ast.If, ast.Compare, ast.Gt, ast.AugAssign, ast.Sub, ast.Return, ast.Constant,
    ast.Assign,
)


def candidate_source(source: str, body: str) -> str:
    if not isinstance(body, str) or not body.strip() or len(body) > 2400:
        raise ValueError("Agent returned an invalid reserve body")
    tree = ast.parse("async def reserve(self, user_id):\n" + indent(body, "    "))
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_NODES):
            raise ValueError("Patch exceeds the booking exercise's supported Python subset")
        if isinstance(node, ast.Name) and node.id not in {"self", "user_id", "available"}:
            raise ValueError("Unsupported name in booking patch")
        if isinstance(node, ast.Attribute):
            receiver = ast.unparse(node.value)
            if (receiver, node.attr) not in {
                ("self", "_check_eligibility"), ("self", "remaining_seats"), ("self", "confirmed"),
                ("self", "waitlist"), ("self.confirmed", "append"), ("self.waitlist", "append"),
            } or (isinstance(node.ctx, ast.Store) and node.attr != "remaining_seats"):
                raise ValueError("Unsupported attribute in booking patch")
        if isinstance(node, ast.Call) and ast.unparse(node.func) not in {
            "self._check_eligibility", "self.confirmed.append", "self.waitlist.append",
        }:
            raise ValueError("Unsupported call in booking patch")
    original = next(node for node in ast.walk(ast.parse(source))
                    if isinstance(node, ast.AsyncFunctionDef) and node.name == "reserve")
    normalized = ast.unparse(tree.body[0])
    method_body = normalized.partition("\n")[2]
    lines = source.splitlines(keepends=True)
    return "".join(lines[:original.lineno]) + indent(method_body, "    ") + "\n" + "".join(lines[original.end_lineno:])


async def _verify(workspace: Path) -> tuple[int, str]:
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "pytest", "-q", "--runxfail", str(FIXTURE / "test_booking.py"),
        cwd=workspace, env={"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(), timeout=20)
    except (TimeoutError, asyncio.CancelledError):
        process.kill()
        await process.wait()
        raise
    return process.returncode, output.decode(errors="replace")


async def _run_booking_agent(name, payload, schema, workspace, run_agent, cancel, timeout):
    agents = workspace / ".claude" / "agents"
    agents.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO_ROOT / ".claude" / "agents" / f"{name}.md", agents / f"{name}.md")
    spec = AgentSpec(
        prompt=json.dumps(payload, ensure_ascii=False), agent=name, tools=["StructuredOutput"],
        allowed_tools=["StructuredOutput"], json_schema=schema, cwd=workspace, timeout=timeout,
        output_language="Ukrainian",
    )
    result = await run_agent(spec, lambda *_: None, cancel, None)
    if result.status != "succeeded":
        raise RuntimeError(result.error or f"{name}: {result.status}")
    return result.structured


async def plan_booking(report: str, run_agent, cancel: asyncio.Event, timeout: float) -> BookingPlan:
    routes = get_config().jira_routes
    if not routes:
        raise RuntimeError("No Jira routes configured")
    with TemporaryDirectory(prefix="workshop-planning-") as directory:
        output = await _run_booking_agent("workshop-planning", {
            "approved_report": report,
            "routes": {key: route.description for key, route in routes.items()},
            "source": (REPO_ROOT / FIXTURE / "service.py").read_text(encoding="utf-8"),
            "test": (REPO_ROOT / FIXTURE / "test_booking.py").read_text(encoding="utf-8"),
        }, RouteSelection.model_json_schema(), Path(directory), run_agent, cancel, timeout)
    try:
        plan = RouteSelection.model_validate(output)
    except ValidationError as exc:
        raise RuntimeError("Planning agent returned an invalid plan") from exc
    route = routes.get(plan.route) if plan.route else None
    if route is None:
        raise RuntimeError("Planner did not select a configured Jira route")
    return BookingPlan(
        goal=redact(plan.goal), steps=[redact(step) for step in plan.steps],
        acceptance_criteria=[redact(criterion) for criterion in plan.acceptance_criteria],
        route=SelectedRoute(id=plan.route, execution_agent=route.execution_agent, qa_agent=route.qa_agent),
    )


async def repair_booking(report: str, plan: BookingPlan, run_agent, cancel: asyncio.Event, timeout: float) -> dict:
    with TemporaryDirectory(prefix="workshop-booking-") as directory:
        workspace = Path(directory)
        fixture = workspace / FIXTURE
        fixture.mkdir(parents=True)
        source_path = fixture / "service.py"
        source = (REPO_ROOT / FIXTURE / "service.py").read_text(encoding="utf-8")
        source_path.write_text(source, encoding="utf-8")
        shutil.copyfile(REPO_ROOT / FIXTURE / "test_booking.py", fixture / "test_booking.py")
        route = plan.route
        if route is None:
            raise RuntimeError("The booking plan must have a Jira route")
        output = await _run_booking_agent(route.execution_agent, {
            "task": "Implement the saved plan. Return the unindented body of BookingService.reserve(self, user_id) "
                    "with no signature or Markdown. Use only the existing eligibility call, seat counter, "
                    "confirmed/waitlist append, and return statuses. Keep the async eligibility check.",
            "approved_report": report, "plan": plan.model_dump(), "source": source,
            "test": (fixture / "test_booking.py").read_text(encoding="utf-8"),
        }, SCHEMA, workspace, run_agent, cancel, timeout)
        if not isinstance(output, dict):
            return {"status": "failed", "error": "Execution agent returned an invalid patch"}
        try:
            updated = candidate_source(source, output.get("body"))
        except (SyntaxError, ValueError) as exc:
            return {"status": "failed", "error": redact(str(exc))[:1200]}
        source_path.write_text(updated, encoding="utf-8")
        patch = "".join(difflib.unified_diff(source.splitlines(True), updated.splitlines(True),
                                             fromfile=f"a/{FIXTURE}/service.py", tofile=f"b/{FIXTURE}/service.py"))
        code, test_output = await _verify(workspace)
        result = {
            "status": "failed", "summary": redact(str(output.get("summary", "")))[:1200],
            "patch": patch, "test_output": redact(test_output)[:5000], "tests_passed": code == 0,
            "error": "Booking verification did not pass",
        }
        if code != 0 or not patch or cancel.is_set():
            return result
        try:
            review = await _run_booking_agent(route.qa_agent, {
                "plan": plan.model_dump(), "patch": patch, "test_output": result["test_output"],
            }, BookingQA.model_json_schema(), workspace, run_agent, cancel, timeout)
            qa = BookingQA.model_validate(review)
        except ValidationError:
            result["error"] = "QA agent returned an invalid verdict"
            return result
        except (OSError, RuntimeError, TimeoutError) as exc:
            result["error"] = redact(str(exc) or type(exc).__name__)[:1200]
            return result
        result["qa"] = {"verdict": qa.verdict, "summary": redact(qa.summary)}
        if qa.verdict == "approved":
            result.update(status="passed", error=None)
        else:
            result["error"] = "QA requested changes"
        return result


def _next_unplanned_handoff(db: Session) -> JiraWorkflowOperation | None:
    row = db.execute(
        select(JiraWorkflowRun, JiraWorkflowDraft)
        .join(JiraWorkflowDraft, JiraWorkflowDraft.run_id == JiraWorkflowRun.run_id)
        .join(JiraWorkflowDecision, JiraWorkflowDecision.draft_id == JiraWorkflowDraft.draft_id)
        .where(
            JiraWorkflowRun.source_kind == "training",
            JiraWorkflowRun.state == JiraWorkflowState.READY_FOR_HANDOFF,
            JiraWorkflowDraft.status == "approved",
            JiraWorkflowDecision.decision == "approve",
            ~select(JiraWorkflowOperation.operation_id).where(
                JiraWorkflowOperation.operation_id == JiraWorkflowRun.run_id + ":booking-repair",
            ).exists(),
        )
        .order_by(JiraWorkflowRun.updated_at, JiraWorkflowRun.run_id, JiraWorkflowDraft.version.desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    run, draft = row
    operation = JiraWorkflowOperation(
        operation_id=f"{run.run_id}:booking-repair", run_id=run.run_id, kind=KIND,
        payload={"approved_report": draft.rendered_append}, attempts=0,
    )
    db.add(operation)
    return operation


def claim_repair(timeout: float) -> tuple[str, int, str, BookingPlan | None] | None:
    with session_scope() as db:
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
        expired = utcnow() - timedelta(seconds=2 * timeout + 60)
        operation = db.scalar(select(JiraWorkflowOperation).where(
            JiraWorkflowOperation.kind == KIND,
            or_(JiraWorkflowOperation.status == "pending", and_(
                JiraWorkflowOperation.status == "planned",
                JiraWorkflowOperation.result["plan"]["route"]["id"].as_string().is_(None),
            ), and_(
                JiraWorkflowOperation.status == "running", JiraWorkflowOperation.updated_at < expired,
            )),
        ).order_by(JiraWorkflowOperation.created_at).limit(1))
        if operation is None:
            operation = _next_unplanned_handoff(db)
        if operation is None:
            return None
        saved_plan = (operation.result or {}).get("plan")
        plan = BookingPlan.model_validate(saved_plan) if saved_plan and saved_plan.get("route") else None
        operation.status = "running"
        operation.attempts += 1
        return operation.operation_id, operation.attempts, operation.payload["approved_report"], plan


async def execute_repair(
    op_id: str, attempt: int, report: str, plan: BookingPlan | None, run_agent, cancel: asyncio.Event, timeout: float,
) -> None:
    planning = plan is None
    try:
        if plan is None:
            plan = await plan_booking(report, run_agent, cancel, timeout)
            result = {"status": "pending"}
        else:
            result = await repair_booking(report, plan, run_agent, cancel, timeout)
    except (OSError, RuntimeError, TimeoutError) as exc:
        result = {"status": "failed", "error": redact(str(exc) or type(exc).__name__)[:1200]}
    with session_scope() as db:
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
        op = db.get(JiraWorkflowOperation, op_id)
        if op is None or op.status != "running" or op.attempts != attempt:
            return
        if cancel.is_set():
            op.status = "pending"
            return
        if plan is not None:
            result["plan"] = plan.model_dump(mode="json")
            if planning and db.get(JiraWorkflowRun, op.run_id).state == JiraWorkflowState.READY_FOR_HANDOFF:
                result["status"] = "planned"
        op.status = result["status"]
        op.result = result
        if "tests_passed" in result:
            db.add(JiraWorkflowEvent(
                run_id=op.run_id, event_id=f"{op_id}:{attempt}:tests", event_type="workshop.booking_tests_result",
                payload={"status": "passed" if result["tests_passed"] else "failed"},
            ))
        if result.get("qa"):
            db.add(JiraWorkflowEvent(
                run_id=op.run_id, event_id=f"{op_id}:{attempt}:qa", event_type="workshop.booking_qa_result",
                payload={"status": result["qa"]["verdict"], "agent_type": plan.route.qa_agent},
            ))
        db.add(JiraWorkflowEvent(
            run_id=op.run_id, event_id=f"{op_id}:{attempt}:result",
            event_type="workshop.booking_plan_result" if planning else "workshop.booking_repair_result",
            payload={"status": "planned" if planning and plan is not None else op.status},
        ))
