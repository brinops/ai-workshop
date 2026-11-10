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

from sqlalchemy import and_, or_, select

from app.config import REPO_ROOT
from app.db import session_scope, utcnow
from app.integrations.claude_runner import AgentSpec
from app.models.jira_workflow import JiraWorkflowEvent, JiraWorkflowOperation
from app.services.redaction import redact

KIND = "booking_repair"
FIXTURE = Path("demo/booking")
SCHEMA = {
    "type": "object",
    "properties": {"body": {"type": "string"}, "summary": {"type": "string"}},
    "required": ["body", "summary"],
    "additionalProperties": False,
}
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


async def repair_booking(report: str, run_agent, cancel: asyncio.Event, timeout: float) -> dict:
    with TemporaryDirectory(prefix="workshop-booking-") as directory:
        workspace = Path(directory)
        fixture = workspace / FIXTURE
        fixture.mkdir(parents=True)
        source_path = fixture / "service.py"
        source = (REPO_ROOT / FIXTURE / "service.py").read_text(encoding="utf-8")
        source_path.write_text(source, encoding="utf-8")
        shutil.copyfile(REPO_ROOT / FIXTURE / "test_booking.py", fixture / "test_booking.py")
        spec = AgentSpec(
            prompt=json.dumps({"task": "Fix the booking race. Return the complete unindented body of "
                               "BookingService.reserve(self, user_id), with no signature or Markdown, "
                               "and a short summary of the code change. The worker reports tests separately. "
                               "Use only the existing eligibility call, seat counter, "
                               "confirmed/waitlist append, and return statuses. Keep the async eligibility check.",
                               "approved_report": report, "source": source,
                               "test": (fixture / "test_booking.py").read_text(encoding="utf-8")}, ensure_ascii=False),
            tools=["StructuredOutput"], allowed_tools=["StructuredOutput"], json_schema=SCHEMA,
            cwd=workspace, timeout=timeout, output_language="Ukrainian",
        )
        result = await run_agent(spec, lambda *_: None, cancel, None)
        if result.status != "succeeded" or not isinstance(result.structured, dict):
            return {"status": "failed", "error": redact(result.error or f"Agent {result.status}")[:1200]}
        try:
            updated = candidate_source(source, result.structured.get("body"))
        except (SyntaxError, ValueError) as exc:
            return {"status": "failed", "error": redact(str(exc))[:1200]}
        source_path.write_text(updated, encoding="utf-8")
        patch = "".join(difflib.unified_diff(source.splitlines(True), updated.splitlines(True),
                                             fromfile=f"a/{FIXTURE}/service.py", tofile=f"b/{FIXTURE}/service.py"))
        code, output = await _verify(workspace)
        return {
            "status": "passed" if code == 0 and patch else "failed",
            "summary": redact(str(result.structured.get("summary", "")))[:1200],
            "patch": patch, "test_output": redact(output)[:5000],
            "error": None if code == 0 and patch else "Booking verification did not pass",
        }


def claim_repair(timeout: float) -> tuple[str, int, str] | None:
    with session_scope() as db:
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
        expired = utcnow() - timedelta(seconds=timeout + 60)
        operation = db.scalar(select(JiraWorkflowOperation).where(
            JiraWorkflowOperation.kind == KIND,
            or_(JiraWorkflowOperation.status == "pending", and_(
                JiraWorkflowOperation.status == "running", JiraWorkflowOperation.updated_at < expired,
            )),
        ).order_by(JiraWorkflowOperation.created_at).limit(1))
        if operation is None:
            return None
        operation.status = "running"
        operation.attempts += 1
        return operation.operation_id, operation.attempts, operation.payload["approved_report"]


async def execute_repair(op_id: str, attempt: int, report: str, run_agent, cancel: asyncio.Event, timeout: float) -> None:
    try:
        result = await repair_booking(report, run_agent, cancel, timeout)
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
        op.status = result["status"]
        op.result = result
        db.add(JiraWorkflowEvent(
            run_id=op.run_id, event_id=f"{op_id}:{attempt}:result", event_type="workshop.booking_repair_result",
            payload={"status": op.status},
        ))
