from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from app.config import REPO_ROOT
from app.db import get_engine, init_engine, run_migrations, session_scope
from app.integrations.training_jira import AppendDescription, JiraIssue, JiraIssueRef, TrainingJira
from app.main import create_app
from app.models.training_jira import TrainingIssue

ROUTE = "/api/jira/training/issues"


def _approval(issue: JiraIssue) -> AppendDescription:
    return AppendDescription(
        operation_id="run-71:draft-71-v2:append",
        issue_ref=JiraIssueRef(**issue.source.model_dump(), issue_id=issue.issue_id),
        expected_reporter_id=issue.reporter_id,
        expected_description_revision=issue.description_revision,
        draft_id="draft-71-v2",
        decision_id="decision-71-v2",
        append_text="Кроки: одночасно забронювати останнє місце з двох акаунтів.",
    )


def _append(command: AppendDescription):
    with session_scope() as db:
        return TrainingJira(db).append_description(command)


def test_training_routes_create_read_and_filter_by_reporter_and_status():
    scenario = json.loads((REPO_ROOT / "demo" / "booking" / "scenario.json").read_text())
    with TestClient(create_app()) as client:
        assert client.get(f"{ROUTE}/template").json() == scenario["issue"]
        first_response = client.post(ROUTE, json={"reporter_id": "reporter-01"})
        assert first_response.status_code == 201
        first = first_response.json()
        second = client.post(ROUTE, json={"reporter_id": "reporter-02"}).json()
        custom = {"title": "Two tabs confirmed the last seat", "description_text": "Both tabs show a confirmation."}
        third_response = client.post(ROUTE, json={"reporter_id": "reporter-01", "issue": custom})
        assert third_response.status_code == 201
        third = third_response.json()
        assert first["schema_version"] == 1 and first["source"]["kind"] == "training"
        assert first["source"] == second["source"] == third["source"]
        assert first["title"] == scenario["issue"]["title"]
        assert first["description_text"] == scenario["issue"]["description_text"]
        assert first["status"] == "new"
        assert third["title"] == custom["title"]
        assert third["description_text"] == custom["description_text"]
        assert third["status"] == "new"
        assert client.get(ROUTE, params={"reporter_id": "reporter-01", "limit": 1}).json() == [first]
        assert client.get(ROUTE, params={"reporter_id": "reporter-01", "after": first["issue_id"]}).json() == [third]
        assert client.get(ROUTE, params={"reporter_id": "reporter-02"}).json() == [second]
        detail = f"{ROUTE}/{first['issue_id']}"
        assert client.get(detail, params={"reporter_id": "reporter-01"}).json() == first
        assert client.get(detail, params={"reporter_id": "reporter-02"}).status_code == 404
        assert client.patch(detail, json={"append_text": "unapproved"}).status_code == 405
        assert client.post(ROUTE, json={"reporter_id": " "}).status_code == 422
        assert client.post(ROUTE, json={"reporter_id": "reporter-01", "issue": {**custom, "title": " "}}).status_code == 422

        with session_scope() as db:
            db.get(TrainingIssue, int(third["issue_id"])).status = "done"
        assert client.get(ROUTE, params={"reporter_id": "reporter-01"}).json() == [first]


def test_approved_append_is_persistent_and_retries_do_not_duplicate():
    with session_scope() as db:
        issue = TrainingJira(db).create_booking_issue("reporter-01")
    approval = _approval(issue)
    with session_scope() as db:
        adapter = TrainingJira(db)
        assert adapter.get_issue(issue.issue_id, issue.reporter_id) == issue
        applied = adapter.append_description(approval)
        assert adapter.append_description(approval).outcome == "already_applied"
        stored = adapter.get_issue(issue.issue_id, issue.reporter_id)
        assert stored is not None and stored.description_text.endswith(approval.append_text)
    assert applied.outcome == "applied"
    assert applied.description_revision != issue.description_revision
    assert applied.operation_id == approval.operation_id

    engine = get_engine()
    url = str(engine.url)
    engine.dispose()
    run_migrations(url)
    init_engine(url)

    repeated = _append(approval)
    assert repeated.outcome == "already_applied" and repeated.description_revision == applied.description_revision
    with session_scope() as db:
        stored = TrainingJira(db).get_issue(issue.issue_id, issue.reporter_id)
        assert stored is not None
        assert stored.description_text == issue.description_text + "\n\n" + approval.append_text
        assert stored.status == "new"
        assert stored.source == issue.source
        assert stored.description_revision == applied.description_revision


def test_append_rejects_wrong_reporter_source_revision_or_operation_reuse():
    with session_scope() as db:
        issue = TrainingJira(db).create_booking_issue("reporter-01")
    approval = _approval(issue)
    assert _append(approval.model_copy(update={"expected_reporter_id": "reporter-02"})).reason == "reporter_mismatch"
    wrong_source = approval.issue_ref.model_copy(update={"instance_id": "foreign"})
    assert _append(approval.model_copy(update={"issue_ref": wrong_source})).reason == "source_mismatch"
    assert _append(approval).outcome == "applied"

    reused = _append(approval.model_copy(update={"append_text": "another block"}))
    assert reused.outcome == "conflict" and reused.reason == "operation_mismatch"
    stale = _append(approval.model_copy(update={"operation_id": "other"}))
    assert stale.outcome == "conflict" and stale.reason == "description_changed"


def test_concurrent_delivery_applies_only_once():
    with session_scope() as db:
        issue = TrainingJira(db).create_booking_issue("reporter-01")
    approval = _approval(issue)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(_append, [approval, approval]))
    assert {result.outcome for result in results} == {"applied", "already_applied"}
    with session_scope() as db:
        stored = TrainingJira(db).get_issue(issue.issue_id, issue.reporter_id)
        assert stored is not None and stored.description_text.count(approval.append_text) == 1
