"""Local Jira workshop records, separate from the PR/CI task lifecycle."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import utcnow
from app.models import Base


class JiraWorkflowState(StrEnum):
    DISCOVERED = "discovered"
    TRIAGING = "triaging"
    WAITING_FOR_REPLY = "waiting_for_reply"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    WAITING_FOR_REVISION = "waiting_for_revision"
    APPROVED = "approved"
    APPLIED = "applied"
    READY_FOR_HANDOFF = "ready_for_handoff"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    NEEDS_INTERVENTION = "needs_intervention"


class JiraWorkflowProfile(Base):
    __tablename__ = "jira_workflow_profiles"
    __table_args__ = (
        UniqueConstraint("local_instance_id", "source_kind", "source_instance_id", name="uq_jira_profile_source"),
    )

    profile_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    local_instance_id: Mapped[str] = mapped_column(String(128))
    source_kind: Mapped[str] = mapped_column(String(32))
    source_instance_id: Mapped[str] = mapped_column(String(128))
    source_reporter_id: Mapped[str] = mapped_column(String(128))
    slack_workspace_id: Mapped[str] = mapped_column(String(128))
    slack_user_id: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class JiraWorkflowRun(Base):
    __tablename__ = "jira_workflow_runs"
    __table_args__ = (
        UniqueConstraint("source_kind", "source_instance_id", "issue_id", name="uq_jira_run_issue"),
        UniqueConstraint("slack_workspace_id", "slack_channel_id", "slack_thread_ts", name="uq_jira_run_thread"),
        CheckConstraint(
            "(slack_workspace_id IS NULL AND slack_channel_id IS NULL AND slack_thread_ts IS NULL) OR "
            "(slack_workspace_id IS NOT NULL AND slack_channel_id IS NOT NULL AND slack_thread_ts IS NOT NULL)",
            name="ck_jira_run_thread_complete",
        ),
        CheckConstraint("follow_up_rounds_used BETWEEN 0 AND 1", name="ck_jira_run_follow_up_rounds"),
    )

    run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey("jira_workflow_profiles.profile_id"))
    source_kind: Mapped[str] = mapped_column(String(32))
    source_instance_id: Mapped[str] = mapped_column(String(128))
    issue_id: Mapped[str] = mapped_column(String(128))
    issue_key: Mapped[str] = mapped_column(String(128))
    # Snapshot the reporter binding at discovery so changing profiles does not retarget a run.
    source_reporter_id: Mapped[str] = mapped_column(String(128))
    slack_user_id: Mapped[str] = mapped_column(String(128))
    slack_workspace_id: Mapped[str | None] = mapped_column(String(128))
    slack_channel_id: Mapped[str | None] = mapped_column(String(128))
    slack_thread_ts: Mapped[str | None] = mapped_column(String(64))
    thread_url: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(32), default=JiraWorkflowState.DISCOVERED, index=True)
    follow_up_rounds_used: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class JiraWorkflowDraft(Base):
    __tablename__ = "jira_workflow_drafts"
    __table_args__ = (
        UniqueConstraint("run_id", "version", name="uq_jira_draft_run_version"),
        UniqueConstraint("run_id", "draft_id", name="uq_jira_draft_run_id"),
        CheckConstraint("version >= 1", name="ck_jira_draft_version"),
    )

    # Project the highest version as current_draft_id, including while waiting for revisions.
    # Approval separately checks the run state and draft status.
    draft_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("jira_workflow_runs.run_id", ondelete="CASCADE"))
    version: Mapped[int]
    status: Mapped[str] = mapped_column(String(32), default="pending_approval")
    based_on_description_revision: Mapped[str] = mapped_column(Text)
    rendered_append: Mapped[str] = mapped_column(Text)
    block: Mapped[dict[str, Any]] = mapped_column(JSON)
    slack_message_ts: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class JiraWorkflowEvent(Base):
    __tablename__ = "jira_workflow_events"
    __table_args__ = (UniqueConstraint("run_id", "event_id", name="uq_jira_event_run_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)  # stable local timeline cursor
    event_id: Mapped[str] = mapped_column(String(255), unique=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("jira_workflow_runs.run_id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime)
    outcome: Mapped[str | None] = mapped_column(String(64))


class JiraWorkflowDecision(Base):
    __tablename__ = "jira_workflow_decisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "draft_id"], ["jira_workflow_drafts.run_id", "jira_workflow_drafts.draft_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["run_id", "source_event_id"], ["jira_workflow_events.run_id", "jira_workflow_events.event_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("decision IN ('approve', 'request_revision')", name="ck_jira_decision_type"),
    )

    decision_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128))
    draft_id: Mapped[str] = mapped_column(String(128), unique=True)
    actor_slack_user_id: Mapped[str] = mapped_column(String(128))
    decision: Mapped[str] = mapped_column(String(32))
    source_event_id: Mapped[str] = mapped_column(String(255), unique=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class JiraWorkflowOperation(Base):
    __tablename__ = "jira_workflow_operations"
    __table_args__ = (
        UniqueConstraint("run_id", "draft_id", "kind", name="uq_jira_operation_draft_kind"),
        ForeignKeyConstraint(
            ["run_id", "draft_id"], ["jira_workflow_drafts.run_id", "jira_workflow_drafts.draft_id"],
            ondelete="CASCADE",
        ),
    )

    operation_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("jira_workflow_runs.run_id", ondelete="CASCADE"), index=True)
    draft_id: Mapped[str | None] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    attempts: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
