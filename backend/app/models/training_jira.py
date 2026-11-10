"""Persistent issues and applied writes for the local training Jira."""

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class TrainingIssue(Base):
    __tablename__ = "training_jira_issues"

    id: Mapped[int] = mapped_column(primary_key=True)
    reporter_id: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="new")
    description: Mapped[str] = mapped_column(Text)
    description_revision: Mapped[int] = mapped_column(default=1)


class TrainingIssueWrite(Base):
    __tablename__ = "training_jira_issue_writes"

    operation_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("training_jira_issues.id"))
    command_digest: Mapped[str] = mapped_column(String(64))
    resulting_revision: Mapped[int]
