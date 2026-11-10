"""Shared router's durable receipts for Slack thread openings."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class SlackThreadOpening(Base):
    __tablename__ = "slack_thread_openings"

    instance_id: Mapped[str] = mapped_column(ForeignKey("slack_pairings.instance_id"), primary_key=True)
    operation_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    request_digest: Mapped[str] = mapped_column(String(64))
    channel_id: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[datetime]
    state: Mapped[str] = mapped_column(String(32))
    thread_ts: Mapped[str | None] = mapped_column(String(64))
    thread_url: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(String(64))
    draft_version: Mapped[int | None]


class SlackRoutedEvent(Base):
    __tablename__ = "slack_routed_events"
    __table_args__ = (Index("ix_slack_routed_events_inbox", "instance_id", "acknowledged_at", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[str] = mapped_column(String(255), unique=True)
    instance_id: Mapped[str] = mapped_column(ForeignKey("slack_pairings.instance_id"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    acknowledged_at: Mapped[datetime | None]
