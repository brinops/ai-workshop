"""Persist training Jira issues and applied writes.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "training_jira_issues",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("reporter_id", sa.String(128), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("description_revision", sa.Integer(), nullable=False),
    )
    op.create_index("ix_training_jira_issues_reporter_id", "training_jira_issues", ["reporter_id"])
    op.create_table(
        "training_jira_issue_writes",
        sa.Column("operation_id", sa.String(255), primary_key=True),
        sa.Column("issue_id", sa.Integer(), sa.ForeignKey("training_jira_issues.id"), nullable=False),
        sa.Column("command_digest", sa.String(64), nullable=False),
        sa.Column("resulting_revision", sa.Integer(), nullable=False),
    )
    op.execute(
        "INSERT INTO settings (key, value, updated_at) "
        "VALUES ('training_jira_source', json_object('instance_id', 'training-' || lower(hex(randomblob(16)))), "
        "CURRENT_TIMESTAMP)"
    )


def downgrade() -> None:
    op.execute("DELETE FROM settings WHERE key = 'training_jira_source'")
    op.drop_table("training_jira_issue_writes")
    op.drop_table("training_jira_issues")
