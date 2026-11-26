"""Plan, implement and verify approved workshop tickets in temporary workspaces."""

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

from app.agents.workshop import BlockerNotice
from app.config import REPO_ROOT
from app.control_plane import AgentName, JiraImplementation, get_config
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
from app.orchestration.workshop_blockers import queue_blocker
from app.services.redaction import redact

KIND = "booking_repair"
FIXTURE = Path("demo/booking")
PAGE = Path("demo/static-page")
PAGE_REVIEW_SKILL = Path(".claude/skills/workshop-page-review")
PAGE_SKILL_PERMISSION = f"Skill({PAGE_REVIEW_SKILL.name})"
PAGE_SCRIPT = PAGE_REVIEW_SKILL / "scripts/check_page.py"
PAGE_REVIEW_COMMAND = f"python3 -I {PAGE_SCRIPT.as_posix()}"
PAGE_CHECK_PASSED = "Static page checks passed."
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
    blocking_reason: PlanText | None = None
    suggested_route: AgentName | None = None


class SelectedRoute(BaseModel):
    id: AgentName
    execution_agent: AgentName
    qa_agent: AgentName
    implementation: JiraImplementation = "booking"


class BookingPlan(PlanContent):
    route: SelectedRoute | None = None


class BookingQA(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Literal["approved", "changes_required"]
    summary: PlanText


class UnsupportedRoute(RuntimeError):
    def __init__(self, notice: BlockerNotice):
        super().__init__(notice.reason)
        self.notice = notice


class StaticPagePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index_html: str = Field(min_length=1, max_length=10000)
    styles_css: str = Field(min_length=1, max_length=6000)
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


async def _verify(workspace: Path, *args: str) -> tuple[int, str]:
    process = await asyncio.create_subprocess_exec(
        sys.executable, *args,
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


async def _run_workshop_agent(name, payload, schema, workspace, run_agent, cancel, timeout,
                              *, page_review=False, emit=None):
    agents = workspace / ".claude" / "agents"
    agents.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO_ROOT / ".claude" / "agents" / f"{name}.md", agents / f"{name}.md")
    tools = ["StructuredOutput"]
    allowed_tools = ["StructuredOutput"]
    if page_review:
        tools.extend(("Skill", "Bash"))
        allowed_tools.extend((PAGE_SKILL_PERMISSION, f"Bash({PAGE_REVIEW_COMMAND})"))
    spec = AgentSpec(
        prompt=json.dumps(payload, ensure_ascii=False), agent=name, tools=tools,
        allowed_tools=allowed_tools, json_schema=schema, cwd=workspace, timeout=timeout,
        output_language="Ukrainian",
    )
    result = await run_agent(spec, emit or (lambda *_: None), cancel, None)
    if result.status != "succeeded":
        raise RuntimeError(result.error or f"{name}: {result.status}")
    return result.structured


async def plan_booking(report: str, run_agent, cancel: asyncio.Event, timeout: float) -> BookingPlan:
    routes = get_config().jira_routes
    if not routes:
        raise RuntimeError("No Jira routes configured")
    with TemporaryDirectory(prefix="workshop-planning-") as directory:
        output = await _run_workshop_agent("workshop-planning", {
            "approved_report": report,
            "routes": {key: route.description for key, route in routes.items()},
            "booking_context": {
                "source": (REPO_ROOT / FIXTURE / "service.py").read_text(encoding="utf-8"),
                "test": (REPO_ROOT / FIXTURE / "test_booking.py").read_text(encoding="utf-8"),
            },
        }, RouteSelection.model_json_schema(), Path(directory), run_agent, cancel, timeout)
    try:
        plan = RouteSelection.model_validate(output)
    except ValidationError as exc:
        raise RuntimeError("Planning agent returned an invalid plan") from exc
    route = routes.get(plan.route) if plan.route else None
    if route is None:
        suggested = routes.get(plan.suggested_route) if plan.suggested_route else None
        if suggested:
            next_step = (
                f"Можу запропонувати маршрут {plan.suggested_route}: {suggested.description} "
                "Підходить цей варіант? Підтвердь або напиши, що хочеш змінити."
            )
        else:
            options = "\n".join(f"• {key}: {route.description}" for key, route in routes.items())
            next_step = f"Доступні варіанти:\n{options}\nНапиши в треді, який варіант і зміни підходять."
        raise UnsupportedRoute(BlockerNotice(
            reason=redact(plan.blocking_reason or "Задача не відповідає можливостям доступних маршрутів."),
            next_step=redact(next_step)[:2200],
        ))
    return BookingPlan(
        goal=redact(plan.goal), steps=[redact(step) for step in plan.steps],
        acceptance_criteria=[redact(criterion) for criterion in plan.acceptance_criteria],
        route=SelectedRoute(id=plan.route, execution_agent=route.execution_agent, qa_agent=route.qa_agent,
                            implementation=route.implementation),
    )


async def _write_booking_patch(workspace, plan, payload, run_agent, cancel, timeout) -> tuple[str, str]:
    fixture = workspace / FIXTURE
    fixture.mkdir(parents=True)
    source_path = fixture / "service.py"
    source = (REPO_ROOT / FIXTURE / "service.py").read_text(encoding="utf-8")
    source_path.write_text(source, encoding="utf-8")
    shutil.copyfile(REPO_ROOT / FIXTURE / "test_booking.py", fixture / "test_booking.py")
    output = await _run_workshop_agent(plan.route.execution_agent, {
        **payload,
        "task": "Implement the saved plan. Return the unindented body of BookingService.reserve(self, user_id) "
                "with no signature or Markdown. Use only the existing eligibility call, seat counter, "
                "confirmed/waitlist append, and return statuses. Keep the async eligibility check.",
        "source": source,
        "test": (fixture / "test_booking.py").read_text(encoding="utf-8"),
    }, SCHEMA, workspace, run_agent, cancel, timeout)
    if not isinstance(output, dict):
        raise ValueError("Execution agent returned an invalid patch")
    updated = candidate_source(source, output.get("body"))
    source_path.write_text(updated, encoding="utf-8")
    patch = "".join(difflib.unified_diff(source.splitlines(True), updated.splitlines(True),
                                         fromfile=f"a/{FIXTURE}/service.py", tofile=f"b/{FIXTURE}/service.py"))
    return patch, str(output.get("summary", ""))


async def _write_page_patch(workspace, plan, payload, run_agent, cancel, timeout) -> tuple[str, str]:
    output = await _run_workshop_agent(plan.route.execution_agent, {
        **payload,
        "task": "Create an offline static page. Return the contents of demo/static-page/index.html "
                "and styles.css. Include a title, main heading, linked local stylesheet and a primary "
                "in-page link to a section. Use HTML and CSS only, without JavaScript or external assets.",
    }, StaticPagePatch.model_json_schema(), workspace, run_agent, cancel, timeout)
    page = StaticPagePatch.model_validate(output)
    (workspace / PAGE).mkdir(parents=True)
    diff = []
    for filename, content in (("index.html", page.index_html), ("styles.css", page.styles_css)):
        relative_path = PAGE / filename
        text = content.rstrip() + "\n"
        (workspace / relative_path).write_text(text, encoding="utf-8")
        diff.extend(difflib.unified_diff([], text.splitlines(True),
                                         fromfile="/dev/null", tofile=f"b/{relative_path}"))
    return "".join(diff), page.summary


async def repair_booking(report: str, plan: BookingPlan, run_agent, cancel: asyncio.Event, timeout: float) -> dict:
    route = plan.route
    if route is None:
        raise RuntimeError("The plan must have a Jira route")
    page_review = route.implementation == "static-page"
    with TemporaryDirectory(prefix="workshop-implementation-") as directory:
        workspace = Path(directory)
        payload = {"approved_report": report, "plan": plan.model_dump()}
        write_patch = _write_page_patch if page_review else _write_booking_patch
        try:
            patch, summary = await write_patch(workspace, plan, payload, run_agent, cancel, timeout)
        except (SyntaxError, ValueError) as exc:
            return {"status": "failed", "error": redact(str(exc))[:1200]}
        if page_review:
            shutil.copytree(REPO_ROOT / PAGE_REVIEW_SKILL, workspace / PAGE_REVIEW_SKILL)
            code, test_output = await _verify(workspace, "-I", str(PAGE_SCRIPT))
        else:
            code, test_output = await _verify(workspace, "-m", "pytest", "-q", "--runxfail",
                                              str(FIXTURE / "test_booking.py"))
        result = {
            "status": "failed", "summary": redact(summary)[:1200],
            "patch": patch, "test_output": redact(test_output)[:5000], "tests_passed": code == 0,
            "error": "Verification did not pass",
        }
        if code != 0 or not patch or cancel.is_set():
            return result
        script_checked = False
        script_called = False

        def review_log(kind: str, summary: str, _detail: str | None = None) -> None:
            nonlocal script_checked, script_called
            if kind == "tool_use" and summary == f"Bash · {PAGE_REVIEW_COMMAND}":
                script_called = True
            if script_called and kind == "tool_result" and summary == PAGE_CHECK_PASSED:
                script_checked = True

        try:
            review = await _run_workshop_agent(route.qa_agent, {
                **payload, "patch": patch, "test_output": result["test_output"],
            }, BookingQA.model_json_schema(), workspace, run_agent, cancel, timeout,
                page_review=page_review, emit=review_log)
            qa = BookingQA.model_validate(review)
        except ValidationError:
            result["error"] = "QA agent returned an invalid verdict"
            return result
        except (OSError, RuntimeError, TimeoutError) as exc:
            result["error"] = redact(str(exc) or type(exc).__name__)[:1200]
            return result
        if page_review:
            result["review_script_checked"] = script_checked
            if not script_checked and qa.verdict == "approved":
                result["error"] = "Reviewer did not complete the static-page skill check"
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
                JiraWorkflowOperation.status == "awaiting_handoff",
                select(JiraWorkflowRun.run_id).where(
                    JiraWorkflowRun.run_id == JiraWorkflowOperation.run_id,
                    JiraWorkflowRun.state == JiraWorkflowState.READY_FOR_HANDOFF,
                ).exists(),
            ), and_(
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
    notice = None
    try:
        if plan is None:
            plan = await plan_booking(report, run_agent, cancel, timeout)
            result = {"status": "pending"}
        else:
            result = await repair_booking(report, plan, run_agent, cancel, timeout)
    except UnsupportedRoute as exc:
        result = {"status": "failed", "error": str(exc)}
        notice = exc.notice
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
            payload={"status": op.status, "error": result.get("error")},
        ))
        if op.status == "failed":
            run = db.get(JiraWorkflowRun, op.run_id)
            assert run is not None
            stage = "planning" if planning else "implementation"
            if notice is None:
                qa = (result.get("qa") or {}).get("summary")
                reason = qa or ("Не вдалося підготувати план." if planning else "Не вдалося завершити реалізацію або перевірку.")
                notice = BlockerNotice(
                    reason=reason,
                    next_step="Напиши в треді, що уточнити або змінити. Щоб повторити спробу з поточними вимогами, скористайся кнопкою на дошці.",
                )
            queue_blocker(db, run, f"{stage}-{attempt}", stage, result.get("error") or notice.reason, notice)
