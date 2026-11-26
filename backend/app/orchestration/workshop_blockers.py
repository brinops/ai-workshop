"""Record a workflow blocker and ask the reporter for a decision in Slack."""

import logging

from sqlalchemy.orm import Session

from app.agents.workshop import BlockerNotice, StageInput
from app.integrations.training_jira import TrainingJira
from app.models.jira_workflow import JiraWorkflowEvent, JiraWorkflowOperation, JiraWorkflowRun, JiraWorkflowState
from app.services.redaction import redact
from app.services.workshop_replies import enqueue_reply

log = logging.getLogger("rcp.worker")


def post_blocker_fallback(db: Session, run: JiraWorkflowRun, key: str, notice: BlockerNotice) -> None:
    enqueue_reply(db, run.run_id, key, f"{notice.reason}\n\n{notice.next_step}"[:3000])


def record_blocker(
    db: Session, run: JiraWorkflowRun, key: str, stage: str, error: str, notice: BlockerNotice | None = None,
) -> None:
    error = redact(error)[:1200]
    run.state, run.last_error = JiraWorkflowState.NEEDS_INTERVENTION, error
    log.warning("Jira workshop %s blocked at %s: %s", run.issue_key, stage, error)
    db.add(JiraWorkflowEvent(
        run_id=run.run_id, event_id=f"{run.run_id}:{key}", event_type="workshop.blocker",
        payload={"stage": stage, "status": "blocked", "error": error, "notice": notice.model_dump() if notice else None},
    ))


def queue_blocker(
    db: Session, run: JiraWorkflowRun, key: str, stage: str, error: str, notice: BlockerNotice,
) -> None:
    key = f"blocker-{key}"
    record_blocker(db, run, key, stage, error, notice)
    if not run.slack_thread_ts:
        return
    issue = TrainingJira(db).get_issue(run.issue_id, run.source_reporter_id)
    if issue is None:
        post_blocker_fallback(db, run, key, notice)
        return
    request = StageInput(stage="blocker", issue=issue, blocker=notice)
    db.add(JiraWorkflowOperation(
        operation_id=f"{run.run_id}:agent:{key}", run_id=run.run_id, kind="agent_stage",
        payload=request.model_dump(mode="json"),
    ))
