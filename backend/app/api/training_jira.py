"""Local API for creating and reading workshop fixtures."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.db import get_db
from app.integrations.training_jira import JiraIssue, ReporterId, TrainingJira

router = APIRouter(prefix="/api/jira/training/issues", tags=["Training Jira"])
Database = Annotated[Session, Depends(get_db)]


class CreateTrainingIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reporter_id: ReporterId


@router.post("", status_code=201)
def create_issue(body: CreateTrainingIssue, db: Database) -> JiraIssue:
    return TrainingJira(db).create_booking_issue(body.reporter_id)


@router.get("")
def list_new_issues(
    db: Database,
    reporter_id: ReporterId,
    after: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> list[JiraIssue]:
    return TrainingJira(db).list_new(reporter_id, after=after, limit=limit)


@router.get("/{issue_id}")
def get_issue(issue_id: str, reporter_id: ReporterId, db: Database) -> JiraIssue:
    issue = TrainingJira(db).get_issue(issue_id, reporter_id)
    if issue is None:
        raise HTTPException(404, "training Jira issue not found")
    return issue
