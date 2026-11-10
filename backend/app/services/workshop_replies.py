"""Queue replies against the recorded Slack thread and immutable draft versions."""

from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from app.integrations.training_jira import JiraIssueRef
from app.integrations.workshop_slack import DraftMessage, ThreadReply
from app.models.jira_workflow import JiraWorkflowDraft, JiraWorkflowOperation, JiraWorkflowRun


def enqueue_reply(db: Session, run_id: str, reply_key: str, text: str, *, draft_id: str | None = None) -> str:
    run = db.get(JiraWorkflowRun, run_id)
    if not run or not run.slack_workspace_id or not run.slack_thread_ts:
        raise ValueError("workshop run has no open Slack thread")
    draft = db.get(JiraWorkflowDraft, draft_id) if draft_id else None
    if draft_id and (not draft or draft.run_id != run_id or draft.status != "pending_approval"):
        raise ValueError("draft is not awaiting approval in this run")
    request = ThreadReply(
        run_id=run_id,
        issue_ref=JiraIssueRef(kind=run.source_kind, instance_id=run.source_instance_id, issue_id=run.issue_id),
        issue_key=run.issue_key,
        slack_workspace_id=run.slack_workspace_id,
        reporter_slack_user_id=run.slack_user_id,
        parent_ts=run.slack_thread_ts,
        reply_key=reply_key,
        text=text,
        draft=DraftMessage(draft_id=draft.draft_id, version=draft.version, rendered_append=draft.rendered_append)
        if draft else None,
    )
    operation_id = request.operation_id
    payload = request.model_dump(mode="json")
    db.execute(
        insert(JiraWorkflowOperation).values(
            operation_id=operation_id, run_id=run_id, draft_id=draft_id, kind="post_reply", payload=payload,
        ).on_conflict_do_nothing(index_elements=[JiraWorkflowOperation.operation_id])
    )
    operation = db.get(JiraWorkflowOperation, operation_id)
    if operation is None or operation.payload != payload:
        raise ValueError("reply operation already exists with different content")
    return operation_id
