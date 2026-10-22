"""Task state machine — the only place where `Task.state` changes."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Task, TaskState
from app.services.events import record_event

S = TaskState

TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    S.NEW: frozenset({S.WAITING_CI, S.NEEDS_REVIEW, S.FAILED}),
    S.WAITING_CI: frozenset({S.ANALYZING, S.DONE, S.NEEDS_REVIEW, S.FAILED, S.WAITING_CI}),
    S.ANALYZING: frozenset({S.TODO, S.NEEDS_REVIEW, S.FAILED, S.WAITING_CI}),
    S.TODO: frozenset({S.IN_PROGRESS, S.ANALYZING, S.NEEDS_REVIEW, S.FAILED, S.WAITING_CI}),
    S.IN_PROGRESS: frozenset({S.VALIDATING, S.NEEDS_REVIEW, S.FAILED, S.WAITING_CI}),
    S.VALIDATING: frozenset({S.DONE, S.ANALYZING, S.NEEDS_REVIEW, S.FAILED, S.WAITING_CI}),
    S.DONE: frozenset({S.WAITING_CI}),
    S.NEEDS_REVIEW: frozenset({S.WAITING_CI, S.ANALYZING, S.TODO, S.FAILED}),
    S.FAILED: frozenset({S.WAITING_CI}),
}

TERMINAL = frozenset({S.DONE, S.FAILED})
# States in which a worker may be running an agent for the task.
AGENT_STATES = frozenset({S.ANALYZING, S.IN_PROGRESS})


class InvalidTransition(ValueError):
    pass


def can_transition(src: str, dst: str) -> bool:
    return TaskState(dst) in TRANSITIONS[TaskState(src)]


def transition(
    db: Session,
    task: Task,
    dst: TaskState,
    reason: str,
    *,
    level: str = "info",
    data: dict | None = None,
) -> None:
    """Move `task` to `dst` or raise InvalidTransition. Records an audit event in the same transaction."""
    src = TaskState(task.state)
    if dst not in TRANSITIONS[src]:
        raise InvalidTransition(f"task {task.id}: {src} -> {dst} is not allowed")
    task.state = dst
    task.pending_action = None
    if dst in TERMINAL or dst == S.NEEDS_REVIEW:
        task.activity = None
    record_event(
        db,
        task.id,
        "state_changed",
        f"{src} → {dst}: {reason}",
        level=level,
        data={"from": src, "to": dst, **(data or {})},
    )
