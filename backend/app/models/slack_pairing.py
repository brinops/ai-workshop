"""Pairings stored by the shared Slack router."""

from datetime import datetime

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class SlackPairing(Base):
    __tablename__ = "slack_pairings"
    __table_args__ = (UniqueConstraint("workspace_id", "slack_user_id", name="uq_slack_pairing_user"),)

    instance_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    token_digest: Mapped[str] = mapped_column(String(64))
    code_digest: Mapped[str | None] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime]
    workspace_id: Mapped[str | None] = mapped_column(String(64))
    slack_user_id: Mapped[str | None] = mapped_column(String(64))
