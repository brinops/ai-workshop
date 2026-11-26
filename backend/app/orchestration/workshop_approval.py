"""Process reporter approvals and apply only the exact saved draft."""

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.workshop import BlockerNotice, StageInput
from app.db import session_scope, utcnow
from app.integrations.training_jira import AppendDescription, JiraIssueRef, TrainingJira
from app.models.jira_workflow import (
    JiraWorkflowDecision,
    JiraWorkflowDraft,
    JiraWorkflowEvent,
    JiraWorkflowOperation,
    JiraWorkflowRun,
)
from app.models.jira_workflow import JiraWorkflowState as State
from app.orchestration.workshop_blockers import queue_blocker
from app.services.slack_inbox import RoutedSlackEvent, local_route_matches

CONFIRMATION_REPLY_KEY = "confirm"


def _earlier_revision(db: Session, event: JiraWorkflowEvent, draft_id: str) -> bool:
    return db.scalar(select(JiraWorkflowEvent.id).where(
        JiraWorkflowEvent.run_id == event.run_id, JiraWorkflowEvent.id < event.id,
        JiraWorkflowEvent.event_type == "slack.draft_action", JiraWorkflowEvent.processed_at.is_(None),
        JiraWorkflowEvent.payload["action"].as_string() == "request_revision",
        JiraWorkflowEvent.payload["draft_id"].as_string() == draft_id,
    ).limit(1)) is not None


def accept_approvals() -> None:
    with session_scope() as db:
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
        events = db.scalars(select(JiraWorkflowEvent).join(JiraWorkflowRun).where(
            JiraWorkflowEvent.event_type == "slack.draft_action", JiraWorkflowEvent.processed_at.is_(None),
            JiraWorkflowEvent.payload["action"].as_string() == "approve",
            JiraWorkflowRun.source_kind == "training",
        ).order_by(JiraWorkflowEvent.id).limit(50)).all()
        for event in events:
            try:
                action = RoutedSlackEvent.model_validate(event.payload)
            except ValidationError:
                event.outcome, event.processed_at = "invalid_event", utcnow()
                continue
            run = db.get(JiraWorkflowRun, event.run_id)
            assert run is not None
            latest = db.scalar(select(JiraWorkflowDraft).where(JiraWorkflowDraft.run_id == run.run_id)
                               .order_by(JiraWorkflowDraft.version.desc()).limit(1))
            if not local_route_matches(db, action):
                event.outcome = "actor_mismatch" if action.actor_slack_user_id != run.slack_user_id else "stale_draft"
            elif latest is None or latest.draft_id != action.draft_id:
                event.outcome = "stale_draft"
            elif latest.status == "approved":
                event.outcome = "duplicate_approval"
            elif run.state != State.WAITING_FOR_APPROVAL or latest.status != "pending_approval":
                event.outcome = "stale_draft"
            elif _earlier_revision(db, event, latest.draft_id):
                continue
            else:
                _approve(db, run, latest, event)
            event.processed_at = utcnow()


def _append_command(run: JiraWorkflowRun, draft: JiraWorkflowDraft, decision_id: str) -> AppendDescription:
    return AppendDescription(
        operation_id=f"{run.run_id}:{draft.draft_id}:append",
        issue_ref=JiraIssueRef(kind=run.source_kind, instance_id=run.source_instance_id, issue_id=run.issue_id),
        expected_reporter_id=run.source_reporter_id,
        expected_description_revision=draft.based_on_description_revision,
        draft_id=draft.draft_id, decision_id=decision_id, append_text=draft.rendered_append,
    )


def _approve(db: Session, run: JiraWorkflowRun, draft: JiraWorkflowDraft, event: JiraWorkflowEvent) -> None:
    decision_id = f"approval-{event.id}"
    command = _append_command(run, draft, decision_id)
    db.add(JiraWorkflowDecision(
        decision_id=decision_id, run_id=run.run_id, draft_id=draft.draft_id, actor_slack_user_id=run.slack_user_id,
        decision="approve", source_event_id=event.event_id,
    ))
    db.add(JiraWorkflowOperation(
        operation_id=command.operation_id, run_id=run.run_id, draft_id=draft.draft_id, kind="append_description",
        payload=command.model_dump(mode="json"),
    ))
    draft.status = "approved"
    run.state = State.APPROVED
    event.outcome = "accepted"


def apply_next_approval() -> None:
    with session_scope() as db:
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
        op = db.scalar(select(JiraWorkflowOperation).where(
            JiraWorkflowOperation.kind == "append_description", JiraWorkflowOperation.status == "pending",
        ).order_by(JiraWorkflowOperation.created_at).limit(1))
        if op is None:
            return
        run = db.get(JiraWorkflowRun, op.run_id)
        assert run is not None
        command = AppendDescription.model_validate(op.payload)
        decision = db.get(JiraWorkflowDecision, command.decision_id)
        draft = db.get(JiraWorkflowDraft, command.draft_id)
        if (run.source_kind != "training" or run.state != State.APPROVED
                or decision is None or decision.decision != "approve"
                or decision.actor_slack_user_id != run.slack_user_id
                or (decision.run_id, decision.draft_id) != (run.run_id, op.draft_id)
                or draft is None or draft.run_id != run.run_id or draft.status != "approved"
                or command.operation_id != op.operation_id
                or command != _append_command(run, draft, decision.decision_id)):
            op.status = "failed"
            op.result = {"reason": "approval_unavailable"}
            return
        jira = TrainingJira(db)
        result = jira.append_description(command)
        op.attempts += 1
        op.result = result.model_dump(mode="json")
        if result.outcome not in ("applied", "already_applied"):
            op.status = result.outcome
            queue_blocker(db, run, f"write-v{draft.version}", "jira", result.reason or result.outcome, BlockerNotice(
                reason=f"Погоджену чернетку v{draft.version} не вдалося записати в Jira.",
                next_step="Напиши в треді, щоб підготувати актуальну чернетку для повторного схвалення.",
            ))
            return

        issue = jira.get_issue(run.issue_id, run.source_reporter_id)
        assert issue is not None
        op.status = "applied"
        run.state = State.APPLIED
        repair = db.get(JiraWorkflowOperation, f"{run.run_id}:booking-repair")
        if repair and repair.status == "failed":
            repair.status = "awaiting_handoff"
            repair.payload = {"approved_report": draft.rendered_append}
            repair.result = None
        request = StageInput(stage="result", issue=issue, write_result=result)
        db.add(JiraWorkflowOperation(
            operation_id=f"{run.run_id}:agent:{CONFIRMATION_REPLY_KEY}-v{draft.version}",
            run_id=run.run_id, kind="agent_stage",
            payload=request.model_dump(mode="json"),
        ))
        db.add(JiraWorkflowEvent(
            event_id=f"{op.operation_id}:applied", run_id=run.run_id, event_type="jira.description_appended",
            payload={"draft_id": command.draft_id, "decision_id": command.decision_id, **op.result},
        ))
