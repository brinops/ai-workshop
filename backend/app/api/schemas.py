"""API request/response models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer

REPO_PATTERN = r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_serializer("*", when_used="json", check_fields=False)
    def _utc(self, v: Any) -> Any:
        if isinstance(v, datetime):
            return v.isoformat(timespec="seconds") + "Z"
        return v


class RegisterIn(BaseModel):
    repo: str = Field(pattern=REPO_PATTERN, max_length=200)
    pr_number: int = Field(gt=0, lt=10_000_000)
    pr_url: str | None = Field(default=None, max_length=500)
    head_sha: str | None = Field(default=None, pattern=r"^[0-9a-f]{7,64}$")
    head_branch: str | None = Field(default=None, max_length=300)
    source: str = Field(default="api", pattern=r"^(hook|webhook|api|cli)$")


class RegisterOut(BaseModel):
    task_id: int
    created: bool
    state: str
    retargeted: bool = False


class TaskCard(_Out):
    id: int
    repo: str
    pr_number: int
    pr_url: str
    title: str
    author: str | None
    head_branch: str
    base_branch: str
    head_sha: str
    expected_sha: str
    source: str
    state: str
    column: str
    pending_action: str | None
    paused: bool
    cancel_requested: bool
    resolution: str | None
    classification: str | None
    confidence: float | None
    root_cause: str | None
    ci_status: str | None
    ci_checked_at: datetime | None
    ci_waiting_since: datetime | None
    ci_next_check_at: datetime | None
    attempt: int
    max_attempts: int
    activity: str | None
    agent_running: bool
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class EventOut(_Out):
    id: int
    task_id: int | None
    ts: datetime
    type: str
    level: str
    message: str
    data: dict | None


class CommentOut(_Out):
    id: int
    ts: datetime
    author: str
    kind: str
    body_md: str
    data: dict | None


class AgentRunOut(_Out):
    id: int
    kind: str
    attempt: int
    status: str
    model: str | None
    session_id: str | None
    exit_code: int | None
    cost_usd: float | None
    num_turns: int | None
    error: str | None
    started_at: datetime
    finished_at: datetime | None
    output: dict | None


class LogLineOut(_Out):
    id: int
    run_id: int
    task_id: int
    ts: datetime
    kind: str
    text: str


class RemediationOut(_Out):
    id: int
    attempt: int
    run_id: int | None
    base_sha: str
    summary: str
    diff: str
    files: list
    scope_ok: bool
    scope_violations: list
    validation_passed: bool
    validation: dict | None
    commit_sha: str | None
    push_status: str
    push_error: str | None
    pushed_at: datetime | None
    created_at: datetime


class ValidationRunOut(_Out):
    id: int
    sha: str
    purpose: str
    valid: bool
    exit_code: int
    report: dict | None
    ts: datetime


class CISnapshotOut(_Out):
    id: int
    sha: str
    overall: str
    checks: list
    ts: datetime


class NotificationOut(_Out):
    id: int
    channel: str
    kind: str
    status: str
    error: str | None
    preview: str | None
    ts: datetime


class TaskDetail(BaseModel):
    task: TaskCard
    actions: list[str]
    events: list[EventOut]
    comments: list[CommentOut]
    runs: list[AgentRunOut]
    remediations: list[RemediationOut]
    validations: list[ValidationRunOut]
    ci: list[CISnapshotOut]
    notifications: list[NotificationOut]


class Board(BaseModel):
    columns: dict[str, list[TaskCard]]
    counts: dict[str, int]
    state_counts: dict[str, int]


class AutomationIn(BaseModel):
    auto_analyze: bool | None = None
    auto_remediate: bool | None = None
    auto_push: bool | None = None


class ActionOut(BaseModel):
    ok: bool
    message: str
    task: TaskCard
