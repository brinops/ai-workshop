"""jira workflow storage

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "jira_workflow_profiles",
        sa.Column("profile_id", sa.String(length=128), nullable=False),
        sa.Column("local_instance_id", sa.String(length=128), nullable=False),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("source_instance_id", sa.String(length=128), nullable=False),
        sa.Column("source_reporter_id", sa.String(length=128), nullable=False),
        sa.Column("slack_workspace_id", sa.String(length=128), nullable=False),
        sa.Column("slack_user_id", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("profile_id"),
        sa.UniqueConstraint("local_instance_id", "source_kind", "source_instance_id", name="uq_jira_profile_source"),
    )
    op.create_table(
        "jira_workflow_runs",
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("profile_id", sa.String(length=128), nullable=False),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("source_instance_id", sa.String(length=128), nullable=False),
        sa.Column("issue_id", sa.String(length=128), nullable=False),
        sa.Column("issue_key", sa.String(length=128), nullable=False),
        sa.Column("source_reporter_id", sa.String(length=128), nullable=False),
        sa.Column("slack_user_id", sa.String(length=128), nullable=False),
        sa.Column("slack_workspace_id", sa.String(length=128), nullable=True),
        sa.Column("slack_channel_id", sa.String(length=128), nullable=True),
        sa.Column("slack_thread_ts", sa.String(length=64), nullable=True),
        sa.Column("thread_url", sa.Text(), nullable=True),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("follow_up_rounds_used", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "(slack_workspace_id IS NULL AND slack_channel_id IS NULL AND slack_thread_ts IS NULL) OR (slack_workspace_id IS NOT NULL AND slack_channel_id IS NOT NULL AND slack_thread_ts IS NOT NULL)",
            name="ck_jira_run_thread_complete",
        ),
        sa.CheckConstraint("follow_up_rounds_used BETWEEN 0 AND 1", name="ck_jira_run_follow_up_rounds"),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["jira_workflow_profiles.profile_id"],
        ),
        sa.PrimaryKeyConstraint("run_id"),
        sa.UniqueConstraint("slack_workspace_id", "slack_channel_id", "slack_thread_ts", name="uq_jira_run_thread"),
        sa.UniqueConstraint("source_kind", "source_instance_id", "issue_id", name="uq_jira_run_issue"),
    )
    op.create_index(op.f("ix_jira_workflow_runs_state"), "jira_workflow_runs", ["state"])

    op.create_table(
        "jira_workflow_drafts",
        sa.Column("draft_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("based_on_description_revision", sa.Text(), nullable=False),
        sa.Column("rendered_append", sa.Text(), nullable=False),
        sa.Column("block", sa.JSON(), nullable=False),
        sa.Column("slack_message_ts", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_jira_draft_version"),
        sa.ForeignKeyConstraint(["run_id"], ["jira_workflow_runs.run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("draft_id"),
        sa.UniqueConstraint("run_id", "draft_id", name="uq_jira_draft_run_id"),
        sa.UniqueConstraint("run_id", "version", name="uq_jira_draft_run_version"),
    )
    op.create_table(
        "jira_workflow_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.Column("outcome", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["jira_workflow_runs.run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
        sa.UniqueConstraint("run_id", "event_id", name="uq_jira_event_run_id"),
    )
    op.create_index(op.f("ix_jira_workflow_events_run_id"), "jira_workflow_events", ["run_id"])

    op.create_table(
        "jira_workflow_decisions",
        sa.Column("decision_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("draft_id", sa.String(length=128), nullable=False),
        sa.Column("actor_slack_user_id", sa.String(length=128), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("source_event_id", sa.String(length=255), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("decision IN ('approve', 'request_revision')", name="ck_jira_decision_type"),
        sa.ForeignKeyConstraint(
            ["run_id", "draft_id"], ["jira_workflow_drafts.run_id", "jira_workflow_drafts.draft_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "source_event_id"],
            ["jira_workflow_events.run_id", "jira_workflow_events.event_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("decision_id"),
        sa.UniqueConstraint("draft_id"),
        sa.UniqueConstraint("source_event_id"),
    )
    op.create_table(
        "jira_workflow_operations",
        sa.Column("operation_id", sa.String(length=255), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("draft_id", sa.String(length=128), nullable=True),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id", "draft_id"], ["jira_workflow_drafts.run_id", "jira_workflow_drafts.draft_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["run_id"], ["jira_workflow_runs.run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("operation_id"),
        sa.UniqueConstraint("run_id", "draft_id", "kind", name="uq_jira_operation_draft_kind"),
    )
    op.create_index(op.f("ix_jira_workflow_operations_run_id"), "jira_workflow_operations", ["run_id"])
    op.create_index(op.f("ix_jira_workflow_operations_status"), "jira_workflow_operations", ["status"])


def downgrade() -> None:
    op.drop_table("jira_workflow_operations")
    op.drop_table("jira_workflow_decisions")
    op.drop_table("jira_workflow_events")
    op.drop_table("jira_workflow_drafts")
    op.drop_table("jira_workflow_runs")
    op.drop_table("jira_workflow_profiles")
