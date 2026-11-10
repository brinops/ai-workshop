"""Local implementation of the Jira source contract used by the workshop."""

from __future__ import annotations

import hashlib
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import String, case, cast, exists, select, update
from sqlalchemy.orm import Session

from app.config import REPO_ROOT
from app.models import Setting
from app.models.training_jira import TrainingIssue, TrainingIssueWrite

PROJECT_KEY = "LAB"
ReporterId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
ReferenceId = Annotated[str, StringConstraints(min_length=1, max_length=128)]
OperationId = Annotated[str, StringConstraints(min_length=1, max_length=255)]
AppendText = Annotated[str, StringConstraints(min_length=1)]


class JiraSource(BaseModel):
    kind: Literal["training", "jira_cloud"]
    instance_id: ReferenceId


class JiraIssueRef(JiraSource):
    issue_id: ReferenceId


class JiraIssue(BaseModel):
    schema_version: Literal[1] = 1
    source: JiraSource
    issue_id: str
    issue_key: str
    project_key: str
    title: str
    status: str
    reporter_id: str
    description_text: str
    description_revision: str
    issue_url: str | None = None


class AppendDescription(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    operation_id: OperationId
    issue_ref: JiraIssueRef
    expected_reporter_id: ReporterId
    expected_description_revision: ReferenceId
    draft_id: ReferenceId
    decision_id: ReferenceId
    append_text: AppendText


class AppendResult(BaseModel):
    schema_version: Literal[1] = 1
    operation_id: str
    outcome: Literal["applied", "already_applied", "conflict", "failed", "unknown"]
    reason: str | None = None
    description_revision: str | None = None


class BookingIssueTemplate(BaseModel):
    title: str
    description_text: str


class BookingScenario(BaseModel):
    issue: BookingIssueTemplate


@lru_cache(maxsize=1)
def _booking_template() -> BookingIssueTemplate:
    path = REPO_ROOT / "demo" / "booking" / "scenario.json"
    return BookingScenario.model_validate_json(path.read_text(encoding="utf-8")).issue


def _revision(issue_id: int, version: int) -> str:
    return f"training:{issue_id}:{version}"


class TrainingJira:
    def __init__(self, db: Session):
        self.db = db

    def source(self) -> JiraSource:
        setting = self.db.get(Setting, "training_jira_source")
        if setting is None:
            raise RuntimeError("training Jira source is missing; run database migrations")
        return JiraSource(kind="training", instance_id=setting.value["instance_id"])

    def _issue(self, source: JiraSource, row: TrainingIssue) -> JiraIssue:
        return JiraIssue(
            source=source,
            issue_id=str(row.id),
            issue_key=f"{PROJECT_KEY}-{row.id}",
            project_key=PROJECT_KEY,
            title=row.title,
            status=row.status,
            reporter_id=row.reporter_id,
            description_text=row.description,
            description_revision=_revision(row.id, row.description_revision),
        )

    def create_booking_issue(self, reporter_id: ReporterId) -> JiraIssue:
        source = self.source()
        template = _booking_template()
        row = TrainingIssue(reporter_id=reporter_id, title=template.title, description=template.description_text)
        self.db.add(row)
        self.db.flush()
        return self._issue(source, row)

    def list_new(self, reporter_id: ReporterId, *, after: int = 0, limit: int = 100) -> list[JiraIssue]:
        rows = self.db.scalars(
            select(TrainingIssue)
            .where(
                TrainingIssue.reporter_id == reporter_id,
                TrainingIssue.status == "new",
                TrainingIssue.id > after,
            )
            .order_by(TrainingIssue.id)
            .limit(limit)
        ).all()
        source = self.source()
        return [self._issue(source, row) for row in rows]

    def get_issue(self, issue_id: str, reporter_id: ReporterId) -> JiraIssue | None:
        row = self.db.scalar(
            select(TrainingIssue).where(cast(TrainingIssue.id, String) == issue_id, TrainingIssue.reporter_id == reporter_id)
        )
        return self._issue(self.source(), row) if row is not None else None

    def append_description(self, command: AppendDescription) -> AppendResult:
        """Apply an approved command from the workflow in the current transaction.

        The caller authenticates the reporter and creates the approval. This adapter enforces the
        target, revision, and idempotency boundary of the write.
        """
        operation_id = command.operation_id
        if command.issue_ref.kind != "training":
            return AppendResult(operation_id=operation_id, outcome="failed", reason="source_mismatch")

        issue_id = command.issue_ref.issue_id
        # Compare the revision as a whole against values derived from the selected issue.
        # Start with a write so competing SQLite transactions serialize before reading the ledger.
        applied = self.db.execute(
            update(TrainingIssue)
            .where(
                cast(TrainingIssue.id, String) == issue_id,
                TrainingIssue.reporter_id == command.expected_reporter_id,
                ("training:" + cast(TrainingIssue.id, String) + ":" + cast(TrainingIssue.description_revision, String))
                == command.expected_description_revision,
                exists().where(
                    Setting.key == "training_jira_source",
                    Setting.value["instance_id"].as_string() == command.issue_ref.instance_id,
                ),
                ~exists().where(TrainingIssueWrite.operation_id == operation_id),
            )
            .values(
                description=case(
                    (TrainingIssue.description == "", command.append_text),
                    else_=TrainingIssue.description + "\n\n" + command.append_text,
                ),
                description_revision=TrainingIssue.description_revision + 1,
            )
            .returning(TrainingIssue.id, TrainingIssue.description_revision)
        ).one_or_none()
        digest = hashlib.sha256(command.model_dump_json().encode()).hexdigest()
        if applied is not None:
            updated_id, revision = applied
            self.db.add(TrainingIssueWrite(
                operation_id=operation_id, issue_id=updated_id, command_digest=digest, resulting_revision=revision,
            ))
            self.db.flush()
            return AppendResult(
                operation_id=operation_id, outcome="applied", description_revision=_revision(updated_id, revision),
            )
        previous = self.db.get(TrainingIssueWrite, operation_id)
        if previous is not None:
            if previous.command_digest != digest:
                return AppendResult(operation_id=operation_id, outcome="conflict", reason="operation_mismatch")
            return AppendResult(
                operation_id=operation_id, outcome="already_applied",
                description_revision=_revision(previous.issue_id, previous.resulting_revision),
            )
        if self.source().instance_id != command.issue_ref.instance_id:
            return AppendResult(operation_id=operation_id, outcome="failed", reason="source_mismatch")
        row = self.db.scalar(select(TrainingIssue).where(cast(TrainingIssue.id, String) == issue_id))
        if row is None:
            return AppendResult(operation_id=operation_id, outcome="failed", reason="issue_not_found")
        reason = "reporter_mismatch" if row.reporter_id != command.expected_reporter_id else "description_changed"
        return AppendResult(operation_id=operation_id, outcome="conflict", reason=reason)
