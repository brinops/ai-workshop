"""tasks remember which control-plane.yaml route (CI check) handles them

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-22
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("tasks") as batch:
        batch.add_column(sa.Column("route", sa.String(length=200), nullable=True))
    # Every task created before routing existed was handled by the Helm route.
    op.execute("UPDATE tasks SET route = 'helm-validate' WHERE route IS NULL AND classification IS NOT NULL")


def downgrade() -> None:
    with op.batch_alter_table("tasks") as batch:
        batch.drop_column("route")
