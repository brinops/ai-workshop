from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select

from app.config import get_settings
from app.db import get_engine, init_engine, session_scope
from app.integrations.training_jira import TrainingJira
from app.models.jira_workflow import JiraWorkflowEvent, JiraWorkflowOperation, JiraWorkflowProfile, JiraWorkflowRun
from app.models.training_jira import TrainingIssue
from app.orchestration import jira_scheduler
from app.orchestration.worker import Worker


def _seed():
    with session_scope() as db:
        jira = TrainingJira(db)
        source = jira.source()
        for name in ("active", "other"):
            db.add(JiraWorkflowProfile(
                profile_id=f"profile-{name}",
                local_instance_id=f"local-{name}",
                source_kind=source.kind,
                source_instance_id=source.instance_id,
                source_reporter_id=f"reporter-{name}",
                slack_workspace_id="TWORK",
                slack_user_id=f"U-{name}",
            ))
        issue = jira.create_booking_issue("reporter-active")
        jira.create_booking_issue("reporter-other")
        closed = jira.create_booking_issue("reporter-active")
        db.get(TrainingIssue, int(closed.issue_id)).status = "done"
        return issue


async def test_worker_tick_and_restart_queue_one_thread_per_new_issue(monkeypatch):
    issue = _seed()
    monkeypatch.setenv("JIRA_WORKSHOP_PROFILE_ID", "profile-active")
    monkeypatch.setenv("JIRA_WORKSHOP_POLL_INTERVAL_SECONDS", "0")
    get_settings.cache_clear()
    worker = Worker()
    await worker.tick()
    await worker.tick()

    with session_scope() as db:
        run = db.scalars(select(JiraWorkflowRun)).one()
        assert run.issue_id == issue.issue_id
        assert run.profile_id == "profile-active"
        assert run.state == "discovered"
        assert run.slack_thread_ts is None
        op = db.scalars(select(JiraWorkflowOperation)).one()
        assert (op.operation_id, op.kind, op.status) == (f"{run.run_id}:thread", "open_thread", "pending")
        assert op.payload["issue_ref"] == {**issue.source.model_dump(), "issue_id": issue.issue_id}
        assert op.payload["reporter_slack_user_id"] == "U-active"
        assert db.scalars(select(JiraWorkflowEvent)).one().event_type == "jira.issue_discovered"
        run.state = "ready_for_handoff"
        second = TrainingJira(db).create_booking_issue("reporter-active")

    engine = get_engine()
    url = str(engine.url)
    engine.dispose()
    init_engine(url)
    await Worker().tick()

    with session_scope() as db:
        assert {r.issue_id: r.state for r in db.scalars(select(JiraWorkflowRun))} == {
            issue.issue_id: "ready_for_handoff", second.issue_id: "discovered",
        }
        assert len(db.scalars(select(JiraWorkflowOperation)).all()) == 2
        assert len(db.scalars(select(JiraWorkflowEvent)).all()) == 2


def test_parallel_discovery_queues_once():
    _seed()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(jira_scheduler.discover_training_page, "profile-active", 0)
        second = pool.submit(jira_scheduler.discover_training_page, "profile-active", 0)
        assert first.result() == second.result() == 0
    with session_scope() as db:
        run = db.scalars(select(JiraWorkflowRun)).one()
        assert db.scalars(select(JiraWorkflowOperation)).one().run_id == run.run_id
        assert db.scalars(select(JiraWorkflowEvent)).one().run_id == run.run_id


async def test_worker_paginates_without_starving_new_issues(monkeypatch):
    first = _seed()
    with session_scope() as db:
        second = TrainingJira(db).create_booking_issue("reporter-active")
    monkeypatch.setattr(jira_scheduler, "PAGE_SIZE", 1)
    monkeypatch.setenv("JIRA_WORKSHOP_PROFILE_ID", "profile-active")
    monkeypatch.setenv("JIRA_WORKSHOP_POLL_INTERVAL_SECONDS", "0")
    get_settings.cache_clear()
    worker = Worker()
    await worker.tick()
    with session_scope() as db:
        assert db.scalars(select(JiraWorkflowRun.issue_id)).one() == first.issue_id
    await worker.tick()
    with session_scope() as db:
        assert set(db.scalars(select(JiraWorkflowRun.issue_id))) == {first.issue_id, second.issue_id}
