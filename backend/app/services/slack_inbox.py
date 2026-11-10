"""Normalize authenticated Slack events and persist them in a workflow inbox."""

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from app.db import session_scope
from app.models.jira_workflow import JiraWorkflowDraft, JiraWorkflowEvent, JiraWorkflowRun


class SlackInbound(BaseModel):
    event_id: str
    event_type: Literal["slack.thread_reply", "slack.draft_action"]
    actor_slack_user_id: str
    message_ts: str
    text: str | None = None
    draft_id: str | None = None
    draft_version: int | None = None
    action: Literal["approve", "request_revision"] | None = None
    action_ts: str | None = None


class SlackRoute(BaseModel):
    workspace_id: str
    channel_id: str
    thread_ts: str


class RoutedSlackEvent(SlackInbound):
    schema_version: Literal[1] = 1
    run_id: str
    thread: SlackRoute
    received_at: datetime


def _timestamp(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9]{1,20}\.[0-9]{1,12}", value) is not None


def parse_thread_reply(payload: dict, workspace: str) -> tuple[SlackInbound, str, str] | None:
    event = payload.get("event")
    if payload.get("type") != "event_callback" or payload.get("team_id") != workspace or not isinstance(event, dict):
        return None
    if event.get("type") != "message" or any(event.get(key) for key in ("subtype", "bot_id", "bot_profile")):
        return None
    source_id, channel = payload.get("event_id"), event.get("channel")
    actor, text = event.get("user"), event.get("text")
    parent, message = event.get("thread_ts"), event.get("ts")
    if not _timestamp(parent) or not _timestamp(message) or parent == message:
        return None
    if not all(isinstance(value, str) and value for value in (source_id, channel, actor, text)) or len(source_id) > 128:
        return None
    return SlackInbound(
        event_id=f"slack:{workspace}:message:{source_id}", event_type="slack.thread_reply",
        actor_slack_user_id=actor, message_ts=message, text=text,
    ), channel, parent


def parse_draft_action(payload: dict, workspace: str) -> tuple[SlackInbound, str, str | None] | None:
    if payload.get("type") != "block_actions":
        return None
    team, user, container = (payload.get(key) for key in ("team", "user", "container"))
    actions = payload.get("actions")
    if not all(isinstance(value, dict) for value in (team, user, container)):
        return None
    if team.get("id") != workspace or container.get("type") != "message":
        return None
    if not isinstance(actions, list) or len(actions) != 1 or not isinstance(actions[0], dict):
        return None
    clicked = actions[0]
    action, clicked_at = clicked.get("action_id"), clicked.get("action_ts")
    channel, message, actor = container.get("channel_id"), container.get("message_ts"), user.get("id")
    if action not in ("approve", "request_revision") or not _timestamp(message) or not _timestamp(clicked_at):
        return None
    if not all(isinstance(value, str) and value for value in (channel, actor)):
        return None
    value = clicked.get("value")
    if not isinstance(value, str) or len(value) > 2000:
        return None
    try:
        ref = json.loads(value)
    except ValueError:
        return None
    if not isinstance(ref, dict):
        return None
    draft_id, version = ref.get("draft_id"), ref.get("draft_version")
    if not isinstance(draft_id, str) or not draft_id or len(draft_id) > 128 or type(version) is not int or version < 1:
        return None
    # Slack retries can carry a new envelope ID. action_ts identifies the original click.
    click_id = hashlib.sha256(json.dumps([channel, message, actor, action, clicked_at]).encode()).hexdigest()
    return SlackInbound(
        event_id=f"slack:{workspace}:action:{click_id}", event_type="slack.draft_action",
        actor_slack_user_id=actor, message_ts=message, draft_id=draft_id,
        draft_version=version, action=action, action_ts=clicked_at,
    ), channel, container.get("thread_ts")


def routed_event(event: SlackInbound, run_id: str, workspace: str, channel: str, parent: str) -> RoutedSlackEvent:
    return RoutedSlackEvent(
        **event.model_dump(), run_id=run_id, received_at=datetime.now(UTC),
        thread=SlackRoute(workspace_id=workspace, channel_id=channel, thread_ts=parent),
    )


def store_local_event(db: Session, event: RoutedSlackEvent) -> bool:
    return db.scalar(
        insert(JiraWorkflowEvent).values(
            event_id=event.event_id, run_id=event.run_id, event_type=event.event_type,
            payload=event.model_dump(mode="json", exclude_none=True),
        ).on_conflict_do_nothing(index_elements=[JiraWorkflowEvent.event_id]).returning(JiraWorkflowEvent.id)
    ) is not None


def local_route_matches(db: Session, event: RoutedSlackEvent) -> bool:
    run = db.get(JiraWorkflowRun, event.run_id)
    route = event.thread
    if run is None or (run.slack_workspace_id, run.slack_channel_id, run.slack_thread_ts, run.slack_user_id) != (
        route.workspace_id, route.channel_id, route.thread_ts, event.actor_slack_user_id,
    ):
        return False
    if event.event_type == "slack.thread_reply":
        return True
    draft = db.get(JiraWorkflowDraft, event.draft_id)
    return (draft is not None and draft.run_id == run.run_id and draft.version == event.draft_version
            and draft.slack_message_ts == event.message_ts)


def store_thread_reply(payload: dict, workspace: str) -> bool:
    parsed = parse_thread_reply(payload, workspace)
    if parsed is None:
        return False
    event, channel, parent = parsed
    with session_scope() as db:
        run_id = db.scalar(select(JiraWorkflowRun.run_id).where(
            JiraWorkflowRun.slack_workspace_id == workspace, JiraWorkflowRun.slack_channel_id == channel,
            JiraWorkflowRun.slack_thread_ts == parent, JiraWorkflowRun.slack_user_id == event.actor_slack_user_id,
        ))
        return run_id is not None and store_local_event(db, routed_event(event, run_id, workspace, channel, parent))


def store_draft_action(payload: dict, workspace: str) -> bool:
    parsed = parse_draft_action(payload, workspace)
    if parsed is None:
        return False
    event, channel, parent = parsed
    with session_scope() as db:
        draft = db.get(JiraWorkflowDraft, event.draft_id)
        run = db.get(JiraWorkflowRun, draft.run_id) if draft else None
        if not run or not run.slack_thread_ts or (parent is not None and parent != run.slack_thread_ts):
            return False
        routed = routed_event(event, run.run_id, workspace, channel, run.slack_thread_ts)
        return local_route_matches(db, routed) and store_local_event(db, routed)
