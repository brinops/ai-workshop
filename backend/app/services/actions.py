"""Manual dashboard actions. Each validates the current state and records an audit event."""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy.orm import Session

from app.db import utcnow
from app.models import PendingAction, Task, TaskState
from app.orchestration.state_machine import transition
from app.orchestration.worker import latest_remediation, start_remediation
from app.services.events import record_event

S = TaskState


class Action(StrEnum):
    ANALYZE = "analyze"
    START_REMEDIATION = "start_remediation"
    APPROVE_PUSH = "approve_push"
    RETRY = "retry"
    PAUSE = "pause"
    RESUME = "resume"
    CANCEL = "cancel"
    MARK_REVIEW = "mark_review"


class ActionError(ValueError):
    pass


def available_actions(db: Session, t: Task) -> list[Action]:
    state = S(t.state)
    out: list[Action] = []
    if (state == S.WAITING_CI and t.ci_status == "failure") or state in (S.TODO, S.NEEDS_REVIEW):
        out.append(Action.ANALYZE)
    if state == S.TODO or (state == S.NEEDS_REVIEW and t.classification and t.attempt < t.max_attempts
                           and t.resolution == "not_auto_remediable"):
        out.append(Action.START_REMEDIATION)
    if state == S.IN_PROGRESS:
        rem = latest_remediation(db, t.id, t.attempt)
        if rem and rem.push_status == "pending_approval":
            out.append(Action.APPROVE_PUSH)
    if state in (S.NEEDS_REVIEW, S.FAILED):
        out.append(Action.RETRY)
    if state not in (S.DONE, S.FAILED):
        out.append(Action.RESUME if t.paused else Action.PAUSE)
        out.append(Action.CANCEL)
        if state != S.NEEDS_REVIEW:
            out.append(Action.MARK_REVIEW)
    return out


def perform(db: Session, t: Task, action: Action, actor: str = "dashboard") -> str:
    if action not in available_actions(db, t):
        raise ActionError(f"'{action}' is not available while the task is {t.state}"
                          + (" (paused)" if t.paused else ""))
    who = f"by {actor}"

    if action == Action.ANALYZE:
        t.analysis_runs = 0
        transition(db, t, S.ANALYZING, f"“Analyze Now” {who}")
        return "analysis queued"

    if action == Action.START_REMEDIATION:
        if t.state == S.NEEDS_REVIEW:
            transition(db, t, S.TODO, f"human approved the diagnosis {who}")
        start_remediation(db, t, f"“Start Remediation” {who}")
        return "remediation queued"

    if action == Action.APPROVE_PUSH:
        rem = latest_remediation(db, t.id, t.attempt)
        assert rem is not None
        rem.push_status = "approved"
        t.pending_action = None
        t.activity = f"Push of {rem.commit_sha[:7]} approved — pushing"

        t.updated_at = utcnow()
        record_event(db, t.id, "push_approved", f"Push of {rem.commit_sha[:7]} approved {who}", level="success")
        return "push approved"

    if action == Action.RETRY:
        t.attempt = 0
        t.analysis_runs = 0
        t.cancel_requested = False
        t.paused = False
        t.last_error = None
        t.resolution = None
        t.expected_sha = t.head_sha
        t.ci_status = None
        t.ci_waiting_since = t.ci_next_check_at = utcnow()
        transition(db, t, S.WAITING_CI, f"“Retry” {who} — re-checking CI on {t.head_sha[:7]}")
        return "retry scheduled"

    if action == Action.PAUSE:
        t.paused = True
        record_event(db, t.id, "paused",
                     f"Paused {who}" + (" — the running agent finishes, nothing further starts" if t.lease_owner else ""),
                     level="warning")
        return "paused"

    if action == Action.RESUME:
        t.paused = False
        t.ci_next_check_at = utcnow()
        record_event(db, t.id, "resumed", f"Resumed {who}")
        return "resumed"

    if action == Action.CANCEL:
        running = t.lease_owner is not None
        t.cancel_requested = running
        t.resolution = "cancelled"
        transition(db, t, S.FAILED, f"cancelled {who}" + (" — stopping the running agent" if running else ""),
                   level="warning")
        return "cancelled"

    if action == Action.MARK_REVIEW:
        running = t.lease_owner is not None
        t.cancel_requested = running
        t.resolution = "manual_review"
        transition(db, t, S.NEEDS_REVIEW, f"marked for review {who}", level="warning")
        return "marked for review"

    raise ActionError(f"unknown action {action}")


__all__ = ["Action", "ActionError", "PendingAction", "available_actions", "perform"]
