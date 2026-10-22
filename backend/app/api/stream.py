"""Server-Sent Events: tails the `events` and `agent_log_lines` tables.

Tailing the database (instead of an in-memory bus) means the stream works when the worker
runs in another process and survives restarts; clients resume with `Last-Event-ID`.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.api.schemas import EventOut, LogLineOut
from app.db import session_scope
from app.models import AgentLogLine, Event, Task

router = APIRouter(prefix="/api")


def _cursor(last_event_id: str | None) -> tuple[int, int] | None:
    try:
        ev, ln = (last_event_id or "").split(":")
        return int(ev), int(ln)
    except ValueError:
        return None


def _poll(ev_after: int, ln_after: int, changed_after):
    with session_scope() as db:
        events = db.scalars(select(Event).where(Event.id > ev_after).order_by(Event.id).limit(200)).all()
        lines = db.scalars(select(AgentLogLine).where(AgentLogLine.id > ln_after).order_by(AgentLogLine.id).limit(500)).all()
        changed = db.execute(select(Task.id, Task.updated_at).where(Task.updated_at > changed_after)).all() \
            if changed_after is not None else []
        latest = db.scalar(select(func.max(Task.updated_at)))
        return ([EventOut.model_validate(e) for e in events], [LogLineOut.model_validate(line) for line in lines],
                [tid for tid, _ in changed], latest)


@router.get("/stream")
async def stream(request: Request) -> StreamingResponse:
    cursor = _cursor(request.headers.get("last-event-id") or request.query_params.get("cursor"))
    if cursor is None:
        with session_scope() as db:
            cursor = (db.scalar(select(func.max(Event.id))) or 0, db.scalar(select(func.max(AgentLogLine.id))) or 0)

    async def gen():
        ev_after, ln_after = cursor
        yield f"retry: 2000\nid: {ev_after}:{ln_after}\nevent: hello\ndata: {{}}\n\n"
        idle = 0
        changed_after = None  # first poll only records the high-water mark
        while not await request.is_disconnected():
            events, lines, changed, latest = await asyncio.to_thread(_poll, ev_after, ln_after, changed_after)
            changed_after = latest or changed_after
            for e in events:
                ev_after = e.id
                yield f"id: {ev_after}:{ln_after}\nevent: task_event\ndata: {e.model_dump_json()}\n\n"
            if lines:
                ln_after = lines[-1].id
                payload = json.dumps([json.loads(line.model_dump_json()) for line in lines])
                yield f"id: {ev_after}:{ln_after}\nevent: agent_log\ndata: {payload}\n\n"
            # Task rows that changed without an audit event (e.g. live `activity` updates).
            silent = sorted(set(changed) - {e.task_id for e in events})
            if silent:
                yield f"event: task_changed\ndata: {json.dumps({'task_ids': silent})}\n\n"
            if events or lines:
                idle = 0
            else:
                idle += 1
                if idle % 30 == 0:
                    yield ": keep-alive\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
