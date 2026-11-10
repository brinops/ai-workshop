"""Migration, restart, and uniqueness guarantees for workshop persistence."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_engine, init_engine, run_migrations, session_scope
from app.models import Task
from app.models.jira_workflow import (
    JiraWorkflowDecision,
    JiraWorkflowDraft,
    JiraWorkflowEvent,
    JiraWorkflowOperation,
    JiraWorkflowProfile,
    JiraWorkflowRun,
    JiraWorkflowState,
)


def _profile(kind: str = "training", instance: str = "lab") -> JiraWorkflowProfile:
    return JiraWorkflowProfile(
        profile_id=f"profile-{kind}", local_instance_id="local-01", source_kind=kind,
        source_instance_id=instance, source_reporter_id=f"reporter-{kind}", slack_workspace_id="TWORK01",
        slack_user_id="UWORK01",
    )


def _run(profile: JiraWorkflowProfile, run_id: str, issue_id: str = "71") -> JiraWorkflowRun:
    return JiraWorkflowRun(
        run_id=run_id, profile_id=profile.profile_id, source_kind=profile.source_kind,
        source_instance_id=profile.source_instance_id, issue_id=issue_id, issue_key="LAB-71",
        source_reporter_id=profile.source_reporter_id, slack_user_id=profile.slack_user_id,
    )


def _draft(run_id: str, version: int) -> JiraWorkflowDraft:
    return JiraWorkflowDraft(
        draft_id=f"{run_id}-v{version}", run_id=run_id, version=version,
        based_on_description_revision="training:71:1", rendered_append=f"Уточнення {version}",
        block={"heading": "Уточнення"},
    )


def _event(run_id: str, event_id: str) -> JiraWorkflowEvent:
    return JiraWorkflowEvent(event_id=event_id, run_id=run_id, event_type="slack.draft_action", payload={})


def _decision(run_id: str, draft_id: str, event_id: str) -> JiraWorkflowDecision:
    return JiraWorkflowDecision(
        decision_id=f"decision-{event_id}", run_id=run_id, draft_id=draft_id,
        source_event_id=event_id, actor_slack_user_id="UWORK01", decision="approve",
    )


def _operation(run_id: str, draft_id: str, operation_id: str) -> JiraWorkflowOperation:
    return JiraWorkflowOperation(
        operation_id=operation_id, run_id=run_id, draft_id=draft_id, kind="append", payload={"draft_id": draft_id},
    )


def test_existing_0003_database_upgrades_without_changing_ci_data(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    url = f"sqlite:///{tmp_path / 'existing.db'}"
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "0003")
    engine = create_engine(url)
    try:
        with Session(engine) as db:
            db.add(Task(
                repo="acme/demo", pr_number=7, pr_url="https://github.com/acme/demo/pull/7",
                head_branch="demo/x", head_sha="a" * 40, expected_sha="a" * 40,
            ))
            db.commit()
        run_migrations(url)
        command.check(config)
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0008"
            assert connection.scalar(text("SELECT head_sha FROM tasks WHERE pr_number = 7")) == "a" * 40
            assert connection.scalar(text("SELECT count(*) FROM jira_workflow_runs")) == 0
    finally:
        engine.dispose()


def test_workflow_history_persists_after_restart():
    profile = _profile()
    run = _run(profile, "run-71")
    run.state = JiraWorkflowState.APPROVED
    run.slack_workspace_id = "TWORK01"
    run.slack_channel_id = "CWORK01"
    run.slack_thread_ts = "1794306000.000100"
    first, second = _draft(run.run_id, 1), _draft(run.run_id, 2)
    first.status = "revision_requested"
    second.status = "approved"
    revision, approval = _event(run.run_id, "action-1"), _event(run.run_id, "action-2")
    request = _decision(run.run_id, first.draft_id, revision.event_id)
    request.decision = "request_revision"
    decision = _decision(run.run_id, second.draft_id, approval.event_id)
    operation = _operation(run.run_id, second.draft_id, "run-71:run-71-v2:append")
    with session_scope() as db:
        db.add(profile)
        db.flush()
        db.add(run)
        db.flush()
        db.add_all([first, second, revision, approval])
        db.flush()
        db.add_all([request, decision, operation])

    engine = get_engine()
    url = str(engine.url)
    engine.dispose()
    run_migrations(url)
    init_engine(url)

    with session_scope() as db:
        stored_run = db.get(JiraWorkflowRun, run.run_id)
        assert stored_run.state == JiraWorkflowState.APPROVED
        assert stored_run.slack_thread_ts == "1794306000.000100"
        assert db.get(JiraWorkflowProfile, stored_run.profile_id).source_reporter_id == "reporter-training"
        versions = db.scalars(select(JiraWorkflowDraft).order_by(JiraWorkflowDraft.version)).all()
        assert [(d.version, d.status, d.rendered_append) for d in versions] == [
            (1, "revision_requested", "Уточнення 1"), (2, "approved", "Уточнення 2"),
        ]
        decisions = db.scalars(select(JiraWorkflowDecision).order_by(JiraWorkflowDecision.source_event_id)).all()
        assert [d.decision for d in decisions] == ["request_revision", "approve"]
        assert db.scalar(select(JiraWorkflowEvent).where(JiraWorkflowEvent.event_id == "action-2")).run_id == run.run_id
        stored_operation = db.get(JiraWorkflowOperation, operation.operation_id)
        assert stored_operation.status == "pending" and stored_operation.draft_id == second.draft_id


def test_workflow_keys_prevent_duplicates_and_cross_run_decisions():
    training, cloud = _profile(), _profile("jira_cloud")
    lab_run, cloud_run = _run(training, "lab-run"), _run(cloud, "cloud-run")
    draft = _draft(lab_run.run_id, 1)
    event = _event(lab_run.run_id, "slack-action")
    other_event = _event(cloud_run.run_id, "other-slack-action")
    with session_scope() as db:
        db.add_all([training, cloud])
        db.flush()
        db.add_all([lab_run, cloud_run])
        db.flush()
        db.add_all([draft, event, other_event])
    with session_scope() as db:
        # Same display key and same issue ID are allowed across distinct sources.
        assert db.scalars(select(JiraWorkflowRun.issue_key)).all() == ["LAB-71", "LAB-71"]

    invalid_records = [
        _run(training, "duplicate-run"),
        _event(cloud_run.run_id, event.event_id),
        _decision(lab_run.run_id, draft.draft_id, other_event.event_id),
        _decision(cloud_run.run_id, draft.draft_id, other_event.event_id),
    ]
    for record in invalid_records:
        with pytest.raises(IntegrityError), session_scope() as db:
            db.add(record)

    with session_scope() as db:
        db.add(_event(lab_run.run_id, "retry-click"))
        db.add(_decision(lab_run.run_id, draft.draft_id, event.event_id))
        db.add(_operation(lab_run.run_id, draft.draft_id, "append-once"))
    with pytest.raises(IntegrityError), session_scope() as db:
        db.add(_decision(lab_run.run_id, draft.draft_id, "retry-click"))
    with pytest.raises(IntegrityError), session_scope() as db:
        db.add(_operation(lab_run.run_id, draft.draft_id, "append-once"))
    with pytest.raises(IntegrityError), session_scope() as db:
        db.add(_operation(lab_run.run_id, draft.draft_id, "append-again"))
