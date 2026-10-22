"""REST API."""

from __future__ import annotations

import asyncio
import hmac
import shutil
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import (
    ActionOut,
    AgentRunOut,
    AutomationIn,
    Board,
    CISnapshotOut,
    CommentOut,
    EventOut,
    LogLineOut,
    NotificationOut,
    RegisterIn,
    RegisterOut,
    RemediationOut,
    TaskCard,
    TaskDetail,
    ValidationRunOut,
)
from app.config import get_settings
from app.control_plane import config_path, get_config
from app.db import get_db, utcnow
from app.integrations.github import GitHubClient, GitHubError, pr_info_from_payload, verify_webhook_signature
from app.models import (
    COLUMN_OF,
    AgentLogLine,
    AgentRun,
    CISnapshot,
    Column,
    Comment,
    Event,
    Notification,
    Remediation,
    Task,
    TaskState,
    ValidationRun,
    WorkerHeartbeat,
)
from app.services import actions as actions_svc
from app.services.registration import register_pr
from app.services.settings_store import Automation, get_automation, update_automation

router = APIRouter(prefix="/api")


def card(t: Task) -> TaskCard:
    now = utcnow()
    running = bool(t.lease_owner and t.lease_expires_at and t.lease_expires_at > now
                   and t.state in (TaskState.ANALYZING, TaskState.IN_PROGRESS))
    return TaskCard.model_validate({**{c: getattr(t, c) for c in TaskCard.model_fields if hasattr(t, c)},
                                    "column": COLUMN_OF[TaskState(t.state)], "agent_running": running})


def _check_token(authorization: str | None) -> None:
    token = get_settings().rcp_api_token
    if not token:
        return
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied, token):
        raise HTTPException(401, "invalid or missing bearer token")


def _check_repo(repo: str) -> None:
    if get_config().repository(repo) is None:
        raise HTTPException(403, f"repository {repo} is not configured in control-plane.yaml")


# ---------------------------------------------------------------- registration
@router.post("/tasks/register", response_model=RegisterOut)
async def register(body: RegisterIn, authorization: str | None = Header(default=None),
                   db: Session = Depends(get_db)) -> RegisterOut:
    """Idempotent PR registration (used by the Claude Code hook). PR facts are re-resolved from GitHub."""
    _check_token(authorization)
    _check_repo(body.repo)

    def fetch():
        gh = GitHubClient()
        try:
            return gh.get_pr(body.repo, body.pr_number)
        finally:
            gh.close()

    try:
        pr = await asyncio.to_thread(fetch)
    except GitHubError as exc:
        raise HTTPException(502, f"could not confirm PR on GitHub: {exc}") from exc
    if pr.state != "open":
        raise HTTPException(409, f"PR #{pr.number} is {pr.state}")
    res = register_pr(db, pr, body.source)
    return RegisterOut(task_id=res.task.id, created=res.created, state=res.task.state, retargeted=res.retargeted)


@router.post("/webhooks/github")
async def github_webhook(request: Request, db: Session = Depends(get_db)) -> dict:
    """Secondary ingestion path: GitHub `pull_request` webhook (HMAC-verified)."""
    secret = get_settings().github_webhook_secret
    if not secret:
        raise HTTPException(503, "GITHUB_WEBHOOK_SECRET is not configured")
    body = await request.body()
    if not verify_webhook_signature(secret, body, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(401, "bad signature")
    event = request.headers.get("X-GitHub-Event")
    payload = await request.json()
    if event == "ping":
        return {"ok": True, "pong": True}
    if event != "pull_request" or payload.get("action") not in ("opened", "reopened", "synchronize"):
        return {"ok": True, "ignored": True}
    repo = payload["repository"]["full_name"]
    _check_repo(repo)
    res = register_pr(db, pr_info_from_payload(repo, payload["pull_request"]), "webhook")
    return {"ok": True, "task_id": res.task.id, "created": res.created}


# ---------------------------------------------------------------- tasks
@router.get("/board", response_model=Board)
def board(db: Session = Depends(get_db)) -> Board:
    tasks = db.scalars(select(Task).order_by(Task.updated_at.desc())).all()
    columns: dict[str, list[TaskCard]] = {c.value: [] for c in Column}
    state_counts: dict[str, int] = {s.value: 0 for s in TaskState}
    for t in tasks:
        columns[COLUMN_OF[TaskState(t.state)]].append(card(t))
        state_counts[t.state] += 1
    return Board(columns=columns, counts={k: len(v) for k, v in columns.items()}, state_counts=state_counts)


@router.get("/tasks", response_model=list[TaskCard])
def list_tasks(state: TaskState | None = None, db: Session = Depends(get_db)) -> list[TaskCard]:
    q = select(Task).order_by(Task.updated_at.desc())
    if state:
        q = q.where(Task.state == state)
    return [card(t) for t in db.scalars(q).all()]


def _task_or_404(db: Session, task_id: int) -> Task:
    t = db.get(Task, task_id)
    if t is None:
        raise HTTPException(404, "task not found")
    return t


@router.get("/tasks/{task_id}", response_model=TaskDetail)
def task_detail(task_id: int, db: Session = Depends(get_db)) -> TaskDetail:
    t = _task_or_404(db, task_id)

    def rows(model, order=None):
        return db.scalars(select(model).where(model.task_id == task_id).order_by(order or model.id)).all()

    return TaskDetail(
        task=card(t),
        actions=[a.value for a in actions_svc.available_actions(db, t)],
        events=[EventOut.model_validate(e) for e in rows(Event)],
        comments=[CommentOut.model_validate(c) for c in rows(Comment)],
        runs=[AgentRunOut.model_validate(r) for r in rows(AgentRun)],
        remediations=[RemediationOut.model_validate(r) for r in rows(Remediation)],
        validations=[ValidationRunOut.model_validate(v) for v in rows(ValidationRun)],
        ci=[CISnapshotOut.model_validate(c) for c in rows(CISnapshot)],
        notifications=[NotificationOut.model_validate(n) for n in rows(Notification)],
    )


@router.get("/tasks/{task_id}/runs/{run_id}/logs", response_model=list[LogLineOut])
def run_logs(task_id: int, run_id: int, after: int = 0, limit: int = 2000,
             db: Session = Depends(get_db)) -> list[LogLineOut]:
    q = (select(AgentLogLine).where(AgentLogLine.task_id == task_id, AgentLogLine.run_id == run_id,
                                    AgentLogLine.id > after).order_by(AgentLogLine.id).limit(min(limit, 5000)))
    return [LogLineOut.model_validate(r) for r in db.scalars(q).all()]


@router.post("/tasks/{task_id}/actions/{action}", response_model=ActionOut)
def task_action(task_id: int, action: actions_svc.Action, db: Session = Depends(get_db)) -> ActionOut:
    t = _task_or_404(db, task_id)
    try:
        message = actions_svc.perform(db, t, action)
    except actions_svc.ActionError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.flush()
    return ActionOut(ok=True, message=message, task=card(t))


@router.get("/events", response_model=list[EventOut])
def recent_events(limit: int = 50, db: Session = Depends(get_db)) -> list[EventOut]:
    q = select(Event).order_by(Event.id.desc()).limit(min(limit, 500))
    return [EventOut.model_validate(e) for e in db.scalars(q).all()]


# ---------------------------------------------------------------- settings & health
@router.get("/settings/automation", response_model=Automation)
def get_automation_settings(db: Session = Depends(get_db)) -> Automation:
    return get_automation(db)


@router.put("/settings/automation", response_model=Automation)
def put_automation_settings(body: AutomationIn, db: Session = Depends(get_db)) -> Automation:
    return update_automation(db, **body.model_dump())


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    s = get_settings()
    now = utcnow()
    hb = db.scalars(select(WorkerHeartbeat).order_by(WorkerHeartbeat.ts.desc())).first()
    worker_ok = bool(hb and now - hb.ts < timedelta(seconds=max(30, s.worker_tick_seconds * 10)))
    running = db.scalar(select(func.count()).select_from(AgentRun).where(AgentRun.status == "running")) or 0
    from app.integrations.github import resolve_token

    components = {
        "database": {"ok": True, "detail": "SQLite WAL"},
        "worker": {"ok": worker_ok, "detail": f"heartbeat {int((now - hb.ts).total_seconds())}s ago" if hb else "no heartbeat"},
        "github": {"ok": bool(resolve_token()), "detail": "token available" if resolve_token() else "no GitHub token"},
        "claude": {"ok": bool(s.claude_path), "detail": s.claude_path or f"{s.claude_bin} not found"},
        "helm": {"ok": bool(shutil.which("helm")), "detail": shutil.which("helm") or "not found"},
        "kubeconform": {"ok": bool(shutil.which("kubeconform")), "detail": shutil.which("kubeconform") or "not found"},
        "slack": {"ok": bool(s.slack_webhook_url), "detail": "webhook configured" if s.slack_webhook_url else "SLACK_WEBHOOK_URL not set"},
    }
    return {
        "ok": all(c["ok"] for k, c in components.items() if k in ("database", "worker")),
        "components": components,
        "agents_running": running,
        "repositories": [r.repo for r in get_config().repositories],
        "model": s.claude_model,
    }


@router.get("/config")
def control_plane_config() -> dict:
    """The active control-plane.yaml (repositories → routes). Contains no secrets."""
    return {"path": str(config_path()), **get_config().model_dump()}
