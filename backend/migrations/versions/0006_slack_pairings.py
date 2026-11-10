"""Persist shared Slack pairings.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "slack_pairings",
        sa.Column("instance_id", sa.String(64), primary_key=True),
        sa.Column("token_digest", sa.String(64), nullable=False),
        sa.Column("code_digest", sa.String(64), unique=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("workspace_id", sa.String(64)),
        sa.Column("slack_user_id", sa.String(64)),
        sa.UniqueConstraint("workspace_id", "slack_user_id", name="uq_slack_pairing_user"),
    )


def downgrade() -> None:
    op.drop_table("slack_pairings")
