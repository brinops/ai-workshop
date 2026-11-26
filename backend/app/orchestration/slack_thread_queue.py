"""Deliver queued workshop Slack messages and persist their receipts."""

import asyncio
import logging

import httpx
from sqlalchemy import select, update

from app.config import Settings
from app.db import session_scope
from app.integrations.workshop_slack import OpenThread, ThreadReceipt, ThreadReply
from app.models.jira_workflow import (
    JiraWorkflowDraft,
    JiraWorkflowEvent,
    JiraWorkflowOperation,
    JiraWorkflowProfile,
    JiraWorkflowRun,
)
from app.models.jira_workflow import JiraWorkflowState as State
from app.models.slack_pairing import SlackPairing
from app.orchestration.workshop_approval import CONFIRMATION_REPLY_KEY
from app.services.slack_threads import open_thread
from app.services.workshop_pairing import local_identity
from app.slack_router import digest

log = logging.getLogger("rcp.worker")


async def _request_thread(url: str, identity: dict[str, str], operation_id: str, request: OpenThread) -> ThreadReceipt:
    path = f"{url.rstrip('/')}/pairings/{identity['instance_id']}/threads/{operation_id}"
    async with httpx.AsyncClient(timeout=12, follow_redirects=False) as client:
        result = await client.put(path, headers={"Authorization": f"Bearer {identity['token']}"},
                                  json=request.model_dump(mode="json"))
    result.raise_for_status()
    return ThreadReceipt.model_validate(result.json())


def _open_local_thread(settings: Settings, instance_id: str, operation_id: str, request: OpenThread) -> ThreadReceipt:
    channel, token = settings.workshop_slack_channel_id, settings.workshop_slack_bot_token
    if not channel or not token or settings.workshop_slack_workspace_id != request.slack_workspace_id:
        return ThreadReceipt(state="pending", reason="slack_posting_not_configured")
    with session_scope() as db:
        pairing = db.get(SlackPairing, instance_id)
        if not pairing or (pairing.workspace_id, pairing.slack_user_id) != (
            request.slack_workspace_id, request.reporter_slack_user_id,
        ):
            return ThreadReceipt(state="failed", reason="pairing_mismatch")
    return open_thread(instance_id, operation_id, request, digest(request.model_dump_json()),
                       channel, token.get_secret_value())


async def deliver_next_thread(settings: Settings) -> None:
    with session_scope() as db:
        identity = local_identity(db)
        if identity is None:
            return
        op = db.scalar(
            select(JiraWorkflowOperation)
            .join(JiraWorkflowRun, JiraWorkflowRun.run_id == JiraWorkflowOperation.run_id)
            .join(JiraWorkflowProfile, JiraWorkflowProfile.profile_id == JiraWorkflowRun.profile_id)
            .where(JiraWorkflowOperation.kind.in_(("open_thread", "post_reply")), JiraWorkflowOperation.status == "pending",
                   JiraWorkflowProfile.local_instance_id == identity["instance_id"])
            .order_by(JiraWorkflowOperation.updated_at, JiraWorkflowOperation.operation_id)
            .limit(1)
        )
        if op is None:
            return

    request = (ThreadReply if op.kind == "post_reply" else OpenThread).model_validate(op.payload)
    try:
        if settings.workshop_slack_app_token:
            receipt = await asyncio.to_thread(_open_local_thread, settings, identity["instance_id"],
                                              op.operation_id, request)
        else:
            assert settings.workshop_slack_router_url is not None
            receipt = await _request_thread(settings.workshop_slack_router_url, identity, op.operation_id, request)
    except (httpx.HTTPError, ValueError):
        log.warning("workshop Slack router unavailable for operation %s", op.operation_id)
        receipt = ThreadReceipt(state="pending", reason="router_unavailable")
    if receipt.state == "opened" and not all((receipt.channel_id, receipt.thread_ts, receipt.thread_url)):
        receipt = ThreadReceipt(state="pending", reason="incomplete_router_receipt")
    with session_scope() as db:
        updated = db.execute(
            update(JiraWorkflowOperation)
            .where(JiraWorkflowOperation.operation_id == op.operation_id, JiraWorkflowOperation.status == "pending")
            .values(status=receipt.state, attempts=JiraWorkflowOperation.attempts + 1,
                    result=receipt.model_dump(exclude_none=True))
        )
        if updated.rowcount != 1 or receipt.state == "pending":
            return
        run = db.get(JiraWorkflowRun, op.run_id)
        assert run is not None
        if receipt.state == "opened" and isinstance(request, ThreadReply):
            if request.draft:
                draft = db.get(JiraWorkflowDraft, request.draft.draft_id)
                assert draft is not None and draft.run_id == run.run_id
                draft.slack_message_ts = receipt.thread_ts
            if (request.reply_key == CONFIRMATION_REPLY_KEY
                    or request.reply_key.startswith(f"{CONFIRMATION_REPLY_KEY}-v")) and run.state == State.APPLIED:
                run.state, run.last_error = State.READY_FOR_HANDOFF, None
                event_type = "slack.confirmation_posted"
            else:
                event_type = "slack.reply_posted"
        elif receipt.state == "opened":
            run.slack_workspace_id = request.slack_workspace_id
            run.slack_channel_id = receipt.channel_id
            run.slack_thread_ts = receipt.thread_ts
            run.thread_url = receipt.thread_url
            event_type = "slack.thread_opened"
        else:
            run.last_error = receipt.reason
            if run.state in (State.DISCOVERED, State.WAITING_FOR_REPLY, State.WAITING_FOR_APPROVAL,
                             State.WAITING_FOR_REVISION):
                run.state = State.NEEDS_INTERVENTION
            event_type = "slack.reply_failed" if isinstance(request, ThreadReply) else "slack.thread_open_failed"
        db.add(JiraWorkflowEvent(
            event_id=f"{op.operation_id}:{receipt.state}",
            run_id=run.run_id,
            event_type=event_type,
            payload=receipt.model_dump(exclude_none=True),
        ))
