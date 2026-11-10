"""Persist Slack router inbox events until acknowledged.

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("slack_thread_openings", sa.Column("draft_version", sa.Integer()))
    op.create_table(
        "slack_routed_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.String(255), nullable=False, unique=True),
        sa.Column("instance_id", sa.String(64), sa.ForeignKey("slack_pairings.instance_id"), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime()),
    )
    op.create_index("ix_slack_routed_events_inbox", "slack_routed_events", ["instance_id", "acknowledged_at", "id"])


def downgrade() -> None:
    op.drop_table("slack_routed_events")
    with op.batch_alter_table("slack_thread_openings") as batch:
        batch.drop_column("draft_version")
