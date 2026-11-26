"""Persist a bounded, redacted trace of the tools a workshop agent uses."""

import json
import logging
import re
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError

from app.db import session_scope
from app.integrations.claude_runner import AgentTraceEvent
from app.models.jira_workflow import JiraWorkflowEvent
from app.services.redaction import redact

log = logging.getLogger(__name__)
MAX_TOOL_EVENTS = 120
MAX_DETAIL = 12000
SECRET_FIELD = re.compile(r"(?:^|_)(?:api_?key|token|secret|password|passwd|authorization)$", re.IGNORECASE)


def _safe_value(value):
    if isinstance(value, dict):
        return {
            redact(key): "[REDACTED]" if SECRET_FIELD.search(key) else _safe_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_safe_value(item) for item in value]
    return redact(value) if isinstance(value, str) else value


class WorkshopTrace:
    def __init__(self, run_id: str, stage: str, agent: str, attempt_id: str | None = None):
        self.run_id, self.stage, self.agent = run_id, stage, agent
        self.attempt_id = attempt_id or f"workshop-{uuid4().hex}"
        self._count = 0
        self._calls: dict[str, tuple[str, str]] = {}
        self._delegates: dict[str, str] = {}
        self._seen: set[tuple[str, str]] = set()

    def lifecycle(self, event: str, **payload) -> None:
        self._record(event, event, self.agent, payload)

    def _record(self, suffix: str, event: str, agent: str, payload: dict) -> None:
        try:
            with session_scope() as db:
                db.add(JiraWorkflowEvent(
                    run_id=self.run_id, event_id=f"{self.attempt_id}:{suffix}", event_type=f"workshop.agent_{event}",
                    payload={"attempt_id": self.attempt_id, "stage": self.stage, "agent_type": agent, **payload},
                ))
        except SQLAlchemyError:
            log.warning("Could not persist workshop trace for run %s", self.run_id)

    def __call__(self, event: AgentTraceEvent) -> None:
        if self._count >= MAX_TOOL_EVENTS and event.kind != "structured_output":
            return
        tool_id = event.tool_use_id
        if tool_id:
            key = (event.kind, tool_id)
            if key in self._seen:
                return
            self._seen.add(key)
        self._count += 1
        agent = self._delegates.get(event.parent_tool_use_id, self.agent)
        tool_name = event.tool_name
        data = event.data
        if event.kind == "tool_use":
            if tool_id:
                self._calls[tool_id] = (tool_name or "Tool", agent)
            if tool_name in ("Agent", "Task") and isinstance(data, dict):
                if tool_id and isinstance(data.get("subagent_type"), str):
                    self._delegates[tool_id] = data["subagent_type"]
                data = {key: value for key, value in data.items() if key != "prompt"}
        elif event.kind == "tool_result" and tool_id in self._calls:
            tool_name, agent = self._calls[tool_id]

        if isinstance(data, str):
            try:
                data = json.loads(data)
            except ValueError:
                pass
        safe = _safe_value(data)
        detail = safe if isinstance(safe, str) else json.dumps(safe, ensure_ascii=False, indent=2)
        self._record(f"trace:{self._count}", event.kind, redact(agent)[:120], {
            "trace": {
                "kind": event.kind, "tool_name": redact(tool_name)[:100] or None,
                "tool_use_id": tool_id, "detail": detail[:MAX_DETAIL],
                "truncated": len(detail) > MAX_DETAIL, "is_error": event.is_error,
            },
        })
