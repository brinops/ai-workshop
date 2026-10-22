"""Idempotent PR registration. Both ingestion paths (Claude Code hook and GitHub webhook) end here."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import utcnow
from app.models import Remediation, Task, TaskState
from app.orchestration.state_machine import transition
from app.services.events import record_event


@dataclass(frozen=True)
class PRInfo:
    """Authoritative PR metadata (resolved from GitHub, never taken from the client as-is)."""

    repo: str
    number: int
    url: str
    title: str
    author: str | None
    head_branch: str
    head_sha: str
    base_branch: str
    state: str = "open"


@dataclass
class RegistrationResult:
    task: Task
    created: bool
    retargeted: bool = False


def _our_commits(db: Session, task_id: int) -> set[str]:
    return {
        sha for (sha,) in db.execute(
            select(Remediation.commit_sha).where(Remediation.task_id == task_id, Remediation.commit_sha.is_not(None))
        )
    }


def register_pr(db: Session, pr: PRInfo, source: str) -> RegistrationResult:
    existing = db.scalar(select(Task).where(Task.repo == pr.repo, Task.pr_number == pr.number))
    if existing is None:
        task = Task(
            repo=pr.repo,
            pr_number=pr.number,
            pr_url=pr.url,
            title=pr.title,
            author=pr.author,
            head_branch=pr.head_branch,
            base_branch=pr.base_branch,
            head_sha=pr.head_sha,
            expected_sha=pr.head_sha,
            source=source,
            state=TaskState.NEW,
            max_attempts=get_settings().max_remediation_attempts,
        )
        try:
            with db.begin_nested():
                db.add(task)
                db.flush()
        except IntegrityError:
            # Lost a registration race with another request: fall through to the idempotent path.
            existing = db.scalar(select(Task).where(Task.repo == pr.repo, Task.pr_number == pr.number))
            assert existing is not None
        else:
            record_event(db, task.id, "registered",
                         f"PR #{pr.number} registered via {source} ({pr.head_branch} @ {pr.head_sha[:7]})",
                         level="success", data={"source": source, "sha": pr.head_sha})
            transition(db, task, TaskState.WAITING_CI, "waiting for GitHub Actions")
            task.ci_waiting_since = utcnow()
            task.ci_next_check_at = utcnow()
            return RegistrationResult(task, created=True)

    task = existing
    task.title, task.pr_url, task.author = pr.title, pr.url, pr.author or task.author
    if pr.head_sha == task.head_sha or pr.head_sha in _our_commits(db, task.id):
        record_event(db, task.id, "registration_duplicate", f"Duplicate registration via {source} ignored",
                     data={"source": source, "sha": pr.head_sha})
        return RegistrationResult(task, created=False)

    # A new commit that the control plane did not create — the developer pushed again.
    previous = task.head_sha
    task.head_sha = pr.head_sha
    record_event(db, task.id, "new_commit", f"New developer commit {pr.head_sha[:7]} (was {previous[:7]})",
                 data={"sha": pr.head_sha, "previous": previous})
    state = TaskState(task.state)
    if state in (TaskState.ANALYZING, TaskState.IN_PROGRESS):
        # The running stage notices head_sha != expected_sha when it finishes and re-targets then.
        return RegistrationResult(task, created=False)
    retarget_to_head(db, task, "new developer commit")
    return RegistrationResult(task, created=False, retargeted=True)


def retarget_to_head(db: Session, task: Task, reason: str) -> None:
    task.expected_sha = task.head_sha
    task.attempt = 0
    task.analysis_runs = 0
    task.ci_status = None
    task.classification = task.confidence = task.root_cause = None
    task.resolution = None
    task.ci_waiting_since = utcnow()
    task.ci_next_check_at = utcnow()
    if task.state != TaskState.WAITING_CI:
        transition(db, task, TaskState.WAITING_CI, f"{reason}; tracking {task.head_sha[:7]}")
    else:
        record_event(db, task.id, "retargeted", f"{reason}; tracking {task.head_sha[:7]}")
