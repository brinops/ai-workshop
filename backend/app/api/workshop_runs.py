"""Local Jira Workflow dashboard and handoff controls."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, HttpUrl
from sqlalchemy import String, and_, cast, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.integrations.training_jira import JiraIssue, TrainingJira
from app.models.jira_workflow import (
    JiraWorkflowDecision,
    JiraWorkflowDraft,
    JiraWorkflowEvent,
    JiraWorkflowOperation,
    JiraWorkflowRun,
    JiraWorkflowState,
)
from app.models.training_jira import TrainingIssue
from app.orchestration.booking_repair import BookingPlan

router = APIRouter(prefix="/api/jira/workshop/runs", tags=["Workshop runs"])
Database = Annotated[Session, Depends(get_db)]


class RunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: str
    issue_key: str
    source_kind: str
    state: JiraWorkflowState
    thread_url: HttpUrl | None
    last_error: str | None
    repair_status: str | None = None
    title: str | None = None


class TimelineEntry(BaseModel):
    id: int
    event_type: str
    received_at: datetime
    outcome: str | None
    action: str | None
    draft_version: int | None
    stage: str | None
    agent_type: str | None
    hook_status: str | None
    status: str | None


class DraftSummary(BaseModel):
    version: int
    status: str
    decision: str | None
    decided_at: datetime | None


class RepairResult(BaseModel):
    status: str
    plan: BookingPlan | None = None
    summary: str | None = None
    patch: str | None = None
    test_output: str | None = None
    error: str | None = None


class RunDetail(BaseModel):
    run: RunSummary
    issue: JiraIssue | None
    reporter_slack_id: str
    drafts: list[DraftSummary]
    timeline: list[TimelineEntry]
    repair: RepairResult | None


def summarize(run: JiraWorkflowRun, status: str | None, title: str | None = None) -> RunSummary:
    return RunSummary.model_validate(run).model_copy(update={"repair_status": status, "title": title})


@router.get("")
def list_runs(db: Database) -> list[RunSummary]:
    rows = db.execute(select(JiraWorkflowRun, JiraWorkflowOperation.status, TrainingIssue.title).outerjoin(
        JiraWorkflowOperation, JiraWorkflowOperation.operation_id == JiraWorkflowRun.run_id + ":booking-repair",
    ).outerjoin(TrainingIssue, and_(
        JiraWorkflowRun.source_kind == "training",
        JiraWorkflowRun.issue_id == cast(TrainingIssue.id, String),
        JiraWorkflowRun.source_reporter_id == TrainingIssue.reporter_id,
    )).order_by(JiraWorkflowRun.created_at.desc(), JiraWorkflowRun.run_id))
    return [summarize(run, status, title) for run, status, title in rows]


@router.get("/{run_id}")
def get_run(run_id: str, db: Database) -> RunDetail:
    run = db.get(JiraWorkflowRun, run_id)
    if run is None:
        raise HTTPException(404, "workshop run not found")
    issue = TrainingJira(db).get_issue(run.issue_id, run.source_reporter_id) if run.source_kind == "training" else None
    events = db.scalars(select(JiraWorkflowEvent).where(
        JiraWorkflowEvent.run_id == run_id,
    ).order_by(JiraWorkflowEvent.id))
    drafts = db.execute(select(JiraWorkflowDraft, JiraWorkflowDecision).outerjoin(
        JiraWorkflowDecision, JiraWorkflowDecision.draft_id == JiraWorkflowDraft.draft_id,
    ).where(JiraWorkflowDraft.run_id == run_id).order_by(JiraWorkflowDraft.version))
    repair = db.get(JiraWorkflowOperation, f"{run_id}:booking-repair")
    return RunDetail(
        run=summarize(run, repair.status if repair else None, issue.title if issue else None),
        repair=RepairResult.model_validate(repair.result) if repair and repair.result else None,
        issue=issue,
        reporter_slack_id=run.slack_user_id,
        drafts=[
            DraftSummary(
                version=draft.version, status=draft.status,
                decision=decision.decision if decision else None,
                decided_at=decision.decided_at.replace(tzinfo=UTC) if decision else None,
            )
            for draft, decision in drafts
        ],
        timeline=[
            TimelineEntry(
                id=event.id, event_type=event.event_type, received_at=event.received_at.replace(tzinfo=UTC),
                outcome=event.outcome, action=event.payload.get("action"),
                draft_version=event.payload.get("draft_version"), stage=event.payload.get("stage"),
                agent_type=event.payload.get("agent_type"), hook_status=event.payload.get("hook_status"),
                status=event.payload.get("status"),
            )
            for event in events
        ],
    )


@router.post("/{run_id}/actions/{action}")
def change_handoff_state(run_id: str, action: Literal["start", "finish", "retry-plan"], db: Database) -> RunSummary:
    db.connection().exec_driver_sql("BEGIN IMMEDIATE")
    run = db.get(JiraWorkflowRun, run_id)
    if run is None:
        raise HTTPException(404, "workshop run not found")
    state = JiraWorkflowState
    op_id = f"{run_id}:booking-repair"
    repair = db.get(JiraWorkflowOperation, op_id)
    if action == "finish":
        if run.state == state.DONE:
            return summarize(run, repair.status if repair else None)
        if run.state != state.IN_PROGRESS or not repair or repair.status != "passed":
            raise HTTPException(409, "booking tests must pass before finishing")
        run.state = state.DONE
    elif action == "retry-plan":
        if run.state != state.READY_FOR_HANDOFF or not repair or repair.status != "failed":
            raise HTTPException(409, "there is no failed plan to retry")
        repair.status, repair.result = "pending", None
        return summarize(run, repair.status)
    else:
        if run.state not in (state.READY_FOR_HANDOFF, state.IN_PROGRESS) or run.source_kind != "training":
            raise HTTPException(409, "run is not ready for the training booking repair")
        if run.state == state.IN_PROGRESS and repair and repair.status == "failed" and not (repair.result or {}).get("plan"):
            # An old run may have started planning under the previous handoff flow.
            run.state = state.READY_FOR_HANDOFF
            repair.status, repair.result = "pending", None
            return summarize(run, repair.status)
        if not repair or not (repair.result or {}).get("plan"):
            raise HTTPException(409, "the implementation plan must be ready before starting")
        if run.state == state.IN_PROGRESS and repair.status != "failed":
            return summarize(run, repair.status)
        if repair.status not in ("planned", "failed"):
            raise HTTPException(409, "the implementation plan must be ready before starting")
        repair.status = "pending"
        repair.result = {"status": "pending", "plan": repair.result["plan"]}
        run.state = state.IN_PROGRESS

    event_id = f"{run_id}:handoff:{action}"
    if db.scalar(select(JiraWorkflowEvent.id).where(JiraWorkflowEvent.event_id == event_id)) is None:
        db.add(JiraWorkflowEvent(
            run_id=run_id, event_id=event_id, event_type=f"workshop.handoff_{action}",
            payload={"status": run.state, "action": action},
        ))
    return summarize(run, repair.status)
