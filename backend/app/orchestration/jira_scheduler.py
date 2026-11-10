"""Discover training Jira issues and persist Slack thread intents."""

from uuid import uuid4

from sqlalchemy.dialects.sqlite import insert

from app.db import session_scope
from app.integrations.training_jira import TrainingJira
from app.models.jira_workflow import JiraWorkflowEvent, JiraWorkflowOperation, JiraWorkflowProfile, JiraWorkflowRun

PAGE_SIZE = 100


def discover_training_page(profile_id: str, after: int) -> int:
    """Process one page for the selected profile and return the next scan cursor."""
    with session_scope() as db:
        profile = db.get(JiraWorkflowProfile, profile_id)
        if profile is None:
            raise ValueError("configured Jira workshop profile does not exist")
        if profile.source_kind != "training":
            return 0
        jira = TrainingJira(db)
        if jira.source().instance_id != profile.source_instance_id:
            raise ValueError("configured Jira workshop profile points to a different training source")
        issues = jira.list_new(profile.source_reporter_id, after=after, limit=PAGE_SIZE)

    # Start the write transaction with the conflict-safe insert. Concurrent workers
    # can discover the same issue, but only the winner queues work.
    with session_scope() as db:
        for issue in issues:
            run_id = f"run-{uuid4().hex}"
            created = db.scalar(
                insert(JiraWorkflowRun)
                .values(
                    run_id=run_id,
                    profile_id=profile.profile_id,
                    source_kind=issue.source.kind,
                    source_instance_id=issue.source.instance_id,
                    issue_id=issue.issue_id,
                    issue_key=issue.issue_key,
                    source_reporter_id=profile.source_reporter_id,
                    slack_user_id=profile.slack_user_id,
                )
                .on_conflict_do_nothing(index_elements=["source_kind", "source_instance_id", "issue_id"])
                .returning(JiraWorkflowRun.run_id)
            )
            if created is None:
                continue
            payload = {
                "schema_version": 1,
                "run_id": run_id,
                "issue_ref": {**issue.source.model_dump(), "issue_id": issue.issue_id},
                "issue_key": issue.issue_key,
                "slack_workspace_id": profile.slack_workspace_id,
                "reporter_slack_user_id": profile.slack_user_id,
            }
            db.add(JiraWorkflowOperation(
                operation_id=f"{run_id}:thread",
                run_id=run_id,
                kind="open_thread",
                payload=payload,
            ))
            db.add(JiraWorkflowEvent(
                event_id=f"{run_id}:discovered",
                run_id=run_id,
                event_type="jira.issue_discovered",
                payload=payload,
            ))
    return int(issues[-1].issue_id) if len(issues) == PAGE_SIZE else 0
