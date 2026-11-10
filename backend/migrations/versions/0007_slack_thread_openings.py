"""Persist shared Slack thread opening receipts.

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "slack_thread_openings",
        sa.Column("instance_id", sa.String(64), sa.ForeignKey("slack_pairings.instance_id"), primary_key=True),
        sa.Column("operation_id", sa.String(255), primary_key=True),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("channel_id", sa.String(64), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("thread_ts", sa.String(64)),
        sa.Column("thread_url", sa.Text()),
        sa.Column("reason", sa.String(64)),
    )


def downgrade() -> None:
    op.drop_table("slack_thread_openings")
