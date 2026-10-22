"""Audit events and task comments. Every row is redacted before it is persisted."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models import Comment, Event
from app.services.redaction import redact, redact_obj

log = logging.getLogger("rcp.events")


def record_event(
    db: Session,
    task_id: int | None,
    type_: str,
    message: str,
    *,
    level: str = "info",
    data: dict | None = None,
) -> Event:
    ev = Event(task_id=task_id, type=type_, level=level, message=redact(message), data=redact_obj(data))
    db.add(ev)
    db.flush()
    log.info("task=%s %s %s", task_id, type_, ev.message)
    return ev


def add_comment(db: Session, task_id: int, author: str, kind: str, body_md: str, data: dict | None = None) -> Comment:
    c = Comment(task_id=task_id, author=author, kind=kind, body_md=redact(body_md), data=redact_obj(data))
    db.add(c)
    db.flush()
    record_event(db, task_id, "comment_added", f"{author} posted a {kind}", data={"comment_id": c.id})
    return c
