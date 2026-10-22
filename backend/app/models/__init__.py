"""ORM models. The schema is owned by Alembic (`backend/migrations`)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.db import utcnow


class TaskState(StrEnum):
    NEW = "NEW"
    WAITING_CI = "WAITING_CI"
    ANALYZING = "ANALYZING"
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    VALIDATING = "VALIDATING"
    DONE = "DONE"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    FAILED = "FAILED"


class Column(StrEnum):
    NEW = "NEW"
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"


COLUMN_OF: dict[TaskState, Column] = {
    TaskState.NEW: Column.NEW,
    TaskState.WAITING_CI: Column.NEW,
    TaskState.ANALYZING: Column.NEW,
    TaskState.TODO: Column.TODO,
    TaskState.NEEDS_REVIEW: Column.TODO,
    TaskState.IN_PROGRESS: Column.IN_PROGRESS,
    TaskState.VALIDATING: Column.IN_PROGRESS,
    TaskState.DONE: Column.DONE,
    TaskState.FAILED: Column.DONE,
}


class Classification(StrEnum):
    SYNTAX_ERROR = "SYNTAX_ERROR"
    SCHEMA_VIOLATION = "SCHEMA_VIOLATION"
    LOGICAL_CONFIGURATION_ERROR = "LOGICAL_CONFIGURATION_ERROR"
    NON_REMEDIABLE = "NON_REMEDIABLE"
    UNKNOWN = "UNKNOWN"


class PendingAction(StrEnum):
    ANALYZE = "analyze"
    REMEDIATE = "remediate"
    PUSH = "push"


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[Any]: JSON}


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (UniqueConstraint("repo", "pr_number", name="uq_task_repo_pr"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    repo: Mapped[str] = mapped_column(String(200))
    pr_number: Mapped[int] = mapped_column(Integer)
    pr_url: Mapped[str] = mapped_column(String(500))
    title: Mapped[str] = mapped_column(String(500), default="")
    author: Mapped[str | None] = mapped_column(String(200))
    head_branch: Mapped[str] = mapped_column(String(300))
    base_branch: Mapped[str] = mapped_column(String(300), default="main")
    head_sha: Mapped[str] = mapped_column(String(64))  # latest known head of the PR branch
    expected_sha: Mapped[str] = mapped_column(String(64))  # commit whose CI result we act on
    source: Mapped[str] = mapped_column(String(32), default="api")
    route: Mapped[str | None] = mapped_column(String(200))  # check name selecting skill/agent in control-plane.yaml

    state: Mapped[str] = mapped_column(String(32), default=TaskState.NEW, index=True)
    pending_action: Mapped[str | None] = mapped_column(String(32))
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    resolution: Mapped[str | None] = mapped_column(String(64))
    last_error: Mapped[str | None] = mapped_column(Text)

    attempt: Mapped[int] = mapped_column(Integer, default=0)  # remediation attempts used
    max_attempts: Mapped[int] = mapped_column(Integer, default=2)
    analysis_runs: Mapped[int] = mapped_column(Integer, default=0)  # analysis runs in current stage

    classification: Mapped[str | None] = mapped_column(String(64))
    confidence: Mapped[float | None] = mapped_column(Float)
    root_cause: Mapped[str | None] = mapped_column(Text)

    ci_status: Mapped[str | None] = mapped_column(String(32))
    ci_checked_at: Mapped[datetime | None] = mapped_column(DateTime)
    ci_next_check_at: Mapped[datetime | None] = mapped_column(DateTime)
    ci_waiting_since: Mapped[datetime | None] = mapped_column(DateTime)

    lease_owner: Mapped[str | None] = mapped_column(String(100))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    activity: Mapped[str | None] = mapped_column(String(300))  # what the worker is doing right now

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    type: Mapped[str] = mapped_column(String(64))
    level: Mapped[str] = mapped_column(String(16), default="info")
    message: Mapped[str] = mapped_column(Text)
    data: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    author: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(32))  # diagnosis | remediation | note
    body_md: Mapped[str] = mapped_column(Text)
    data: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))  # analysis | remediation
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="running")
    worker_id: Mapped[str | None] = mapped_column(String(100))
    pid: Mapped[int | None] = mapped_column(Integer)
    model: Mapped[str | None] = mapped_column(String(100))
    session_id: Mapped[str | None] = mapped_column(String(100))
    exit_code: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    num_turns: Mapped[int | None] = mapped_column(Integer)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class AgentLogLine(Base):
    __tablename__ = "agent_log_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[int] = mapped_column(Integer, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    kind: Mapped[str] = mapped_column(String(32))  # system | text | tool_use | tool_result | result | stderr
    text: Mapped[str] = mapped_column(Text)  # one-line summary
    detail: Mapped[str | None] = mapped_column(Text)  # full tool input / output, shown when expanded


class Remediation(Base):
    __tablename__ = "remediations"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    attempt: Mapped[int] = mapped_column(Integer)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"))
    base_sha: Mapped[str] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(Text, default="")
    diff: Mapped[str] = mapped_column(Text, default="")
    files: Mapped[list[Any]] = mapped_column(JSON, default=list)
    scope_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    scope_violations: Mapped[list[Any]] = mapped_column(JSON, default=list)
    validation: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    validation_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    commit_sha: Mapped[str | None] = mapped_column(String(64))
    # pending_approval | approved | pushed | rejected | failed | discarded
    push_status: Mapped[str] = mapped_column(String(32), default="pending_approval")
    push_error: Mapped[str | None] = mapped_column(Text)
    pushed_at: Mapped[datetime | None] = mapped_column(DateTime)
    worktree_path: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ValidationRun(Base):
    """Local deterministic validation executed by the backend (not by GitHub)."""

    __tablename__ = "validation_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    sha: Mapped[str] = mapped_column(String(64))
    purpose: Mapped[str] = mapped_column(String(32))  # pre-analysis | post-remediation
    valid: Mapped[bool] = mapped_column(Boolean)
    exit_code: Mapped[int] = mapped_column(Integer)
    report: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CISnapshot(Base):
    __tablename__ = "ci_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    sha: Mapped[str] = mapped_column(String(64))
    overall: Mapped[str] = mapped_column(String(32))
    checks: Mapped[list[Any]] = mapped_column(JSON, default=list)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(32), default="slack")
    kind: Mapped[str] = mapped_column(String(32))  # remediated | needs_review | failed
    status: Mapped[str] = mapped_column(String(32))  # sent | failed | skipped
    error: Mapped[str | None] = mapped_column(Text)
    preview: Mapped[str | None] = mapped_column(Text)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"

    worker_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    info: Mapped[dict[str, Any] | None] = mapped_column(JSON)
