"""Run one workshop stage through the standard headless Claude process."""

import json
import re
import shutil
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import ValidationError
from sqlalchemy.dialects.sqlite import insert

from app.agents.workshop import EVIDENCE_PATHS, StageInput, StageOutput, claude_output_schema, output_contract
from app.config import REPO_ROOT, get_settings
from app.db import session_scope
from app.integrations.claude_runner import AgentResult, AgentSpec
from app.models.jira_workflow import JiraWorkflowEvent, JiraWorkflowRun
from app.orchestration.workshop_trace import WorkshopTrace
from app.services.redaction import redact

TRIAGE_AGENT = "workshop-triage"
SPECIALISTS = ("workshop-investigation", "workshop-communication", "workshop-action")
TONE_OF_VOICE = Path("skills/workshop-tone-of-voice")
TONE_RUNBOOKS = Path(".claude") / TONE_OF_VOICE / "runbooks"
SUBAGENT_HOOK = Path("hooks/record_subagent.py")


@dataclass
class WorkshopAttempt:
    attempt_id: str
    status: str
    output: StageOutput | None = None
    error: str | None = None


def _prepare_workspace(workspace: Path) -> None:
    source = REPO_ROOT / ".claude"
    profile = workspace / ".claude"
    (profile / "agents").mkdir(parents=True)
    for name in (TRIAGE_AGENT, *SPECIALISTS):
        agent = Path("agents") / f"{name}.md"
        shutil.copyfile(source / agent, profile / agent)
    shutil.copytree(source / TONE_OF_VOICE, profile / TONE_OF_VOICE)
    (profile / SUBAGENT_HOOK.parent).mkdir()
    shutil.copyfile(source / SUBAGENT_HOOK, profile / SUBAGENT_HOOK)

    hooks = json.loads((source / "settings.json").read_text(encoding="utf-8")).get("hooks", {})
    (profile / "settings.json").write_text(json.dumps({
        "env": {"CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1"},
        "hooks": {event: hooks[event] for event in ("SubagentStart", "SubagentStop") if event in hooks},
    }), encoding="utf-8")
    for path in EVIDENCE_PATHS:
        target = workspace / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / path, target)


def _import_subagent_events(workspace: Path, run_id: str, attempt_id: str, stage: str) -> str:
    journal = workspace / ".claude/hooks/subagents.jsonl"
    try:
        lines = journal.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return "no_hook_events"
    except (OSError, UnicodeError):
        return "unreadable_hook_journal"

    records = []
    invalid = False
    for line in lines:
        try:
            row = json.loads(line)
            kind = {"SubagentStart": "started", "SubagentStop": "finished"}[row["kind"]]
            agent_id, role = row["agent_id"], row["agent_type"]
            at = datetime.fromisoformat(row["at"])
            if role not in SPECIALISTS or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", agent_id) or at.tzinfo is None:
                raise ValueError("invalid hook metadata")
        except (ValueError, KeyError, TypeError):
            invalid = True
            continue
        records.append({
            "run_id": run_id, "event_id": f"{attempt_id}:subagent:{agent_id}:{kind}",
            "event_type": f"workshop.subagent_{kind}",
            "received_at": at.astimezone(UTC).replace(tzinfo=None),
            "payload": {"attempt_id": attempt_id, "stage": stage, "agent_id": agent_id, "agent_type": role},
        })
    if records:
        with session_scope() as db:
            db.execute(insert(JiraWorkflowEvent).values(records).on_conflict_do_nothing(
                index_elements=[JiraWorkflowEvent.event_id],
            ))
    return "invalid_hook_records" if invalid else "recorded" if records else "no_hook_events"


async def run_workshop_stage(run_id: str, request: StageInput, cancel,
                             run_agent: Callable[..., Awaitable[AgentResult]]) -> WorkshopAttempt:
    with session_scope() as db:
        run = db.get(JiraWorkflowRun, run_id)
        issue = request.issue
        if run is None or (run.source_kind, run.source_instance_id, run.issue_id) != (
            issue.source.kind, issue.source.instance_id, issue.issue_id,
        ):
            raise ValueError("stage issue does not match the workshop run")
    if request.stage == "revision" and request.previous_block is None:
        raise ValueError("revision requires the previous block")
    if request.stage == "result" and request.write_result is None:
        raise ValueError("result stage requires the actual write outcome")

    trace = WorkshopTrace(run_id, request.stage, TRIAGE_AGENT)
    attempt_id = trace.attempt_id
    trace.lifecycle("started", status="running")
    delegates: list[str] = []

    def emit(kind: str, summary: str, detail: str | None = None) -> None:
        if kind == "tool_use" and detail and summary.startswith(("Agent ·", "Task ·")):
            try:
                role = json.loads(detail).get("subagent_type")
            except (ValueError, AttributeError):
                return
            if role in SPECIALISTS and role not in delegates:
                delegates.append(role)

    result = None
    output = None
    error = None
    status = "failed"
    hook_status = "not_run"
    contract = output_contract(request)
    try:
        with TemporaryDirectory(prefix="jira-workshop-") as directory:
            workspace = Path(directory)
            _prepare_workspace(workspace)
            spec = AgentSpec(
                prompt=json.dumps({
                    **request.model_dump(mode="json", exclude_none=True),
                    "run_id": run_id, "evidence_paths": EVIDENCE_PATHS,
                }, ensure_ascii=False),
                tools=["Agent", "Read", "StructuredOutput"],
                allowed_tools=[*(f"Agent({role})" for role in SPECIALISTS),
                               *(f"Read(./{path})" for path in EVIDENCE_PATHS),
                               f"Read(./{TONE_RUNBOOKS.as_posix()}/*.md)", "StructuredOutput"],
                json_schema=claude_output_schema(contract),
                agent=TRIAGE_AGENT, cwd=workspace, output_language="Ukrainian",
                timeout=get_settings().jira_workshop_agent_timeout_seconds,
                trace=trace,
            )
            try:
                result = await run_agent(spec, emit, cancel, None)
            finally:
                hook_status = _import_subagent_events(workspace, run_id, attempt_id, request.stage)
        status = result.status
        if status == "succeeded":
            output = contract.validate_python(result.structured)
        else:
            error = redact(result.error or f"agent {status}")[:1500]
    except ValidationError as exc:
        status = "failed"
        errors = exc.errors(include_input=False, include_context=False, include_url=False)
        error = "invalid structured output: " + ", ".join(
            f"{'.'.join(map(str, item['loc'])) or 'result'} ({item['type']})" for item in errors
        )[:1000]
    except (OSError, ValueError, RuntimeError) as exc:
        status, error = "failed", redact(f"{type(exc).__name__}: {exc}")[:1500]

    trace.lifecycle(
        "finished",
        status=status, error=error, retryable=status in ("failed", "timeout"),
        hook_status=hook_status, delegated_agents=delegates, model=result.model if result else None,
        exit_code=result.exit_code if result else None,
        permission_denials=len(result.permission_denials) if result else 0,
        output_kind=output.kind if output else None,
    )
    return WorkshopAttempt(attempt_id=attempt_id, status=status, output=output, error=error)
