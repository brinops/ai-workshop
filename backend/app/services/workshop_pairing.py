"""Local pairing credentials and active workshop profile."""

from secrets import token_urlsafe
from uuid import uuid4

from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from app.integrations.training_jira import TrainingJira
from app.models import Setting
from app.models.jira_workflow import JiraWorkflowProfile

IDENTITY_KEY = "jira_workshop_local_identity"
ACTIVE_PROFILE_KEY = "jira_workshop_active_profile"


def active_profile_id(db: Session) -> str | None:
    row = db.get(Setting, ACTIVE_PROFILE_KEY)
    return row.value["profile_id"] if row else None


def local_identity(db: Session, *, create: bool = False) -> dict[str, str] | None:
    if create:
        db.execute(
            insert(Setting).values(
                key=IDENTITY_KEY, value={"instance_id": uuid4().hex, "token": token_urlsafe(32)},
            ).on_conflict_do_nothing(index_elements=[Setting.key])
        )
    row = db.get(Setting, IDENTITY_KEY)
    return row.value if row else None


def activate_training_profile(db: Session, instance_id: str, workspace_id: str, slack_user_id: str) -> JiraWorkflowProfile:
    source = TrainingJira(db).source()
    profile_id = f"profile-{instance_id}"
    db.execute(
        insert(JiraWorkflowProfile).values(
            profile_id=profile_id,
            local_instance_id=instance_id,
            source_kind=source.kind,
            source_instance_id=source.instance_id,
            source_reporter_id=f"reporter-{instance_id}",
            slack_workspace_id=workspace_id,
            slack_user_id=slack_user_id,
        ).on_conflict_do_nothing(index_elements=[JiraWorkflowProfile.profile_id])
    )
    profile = db.get(JiraWorkflowProfile, profile_id)
    assert profile is not None
    if (profile.slack_workspace_id, profile.slack_user_id) != (workspace_id, slack_user_id):
        raise ValueError("confirmed Slack identity differs from the local profile")
    # Refreshing a connected status must not replace a source the user selected later.
    db.execute(
        insert(Setting).values(key=ACTIVE_PROFILE_KEY, value={"profile_id": profile_id})
        .on_conflict_do_nothing(index_elements=[Setting.key])
    )
    return profile
