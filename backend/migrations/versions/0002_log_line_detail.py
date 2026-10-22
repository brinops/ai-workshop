"""agent log lines keep the full tool input / output for the expandable log view

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-22
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("agent_log_lines") as batch:
        batch.add_column(sa.Column("detail", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("agent_log_lines") as batch:
        batch.drop_column("detail")
