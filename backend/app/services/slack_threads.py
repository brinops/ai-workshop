"""Reserve a Slack send before calling Slack, and persist the receipt before linking."""

from datetime import timedelta

import httpx
from sqlalchemy.dialects.sqlite import insert

from app.db import session_scope, utcnow
from app.integrations import workshop_slack
from app.integrations.workshop_slack import OpenThread, SlackRejected, ThreadReceipt, ThreadReply
from app.models.slack_thread import SlackThreadOpening

POST_WINDOW = timedelta(seconds=30)


def open_thread(instance_id: str, operation_id: str, request: OpenThread,
                request_digest: str, channel: str, token: str) -> ThreadReceipt:
    key = (instance_id, operation_id)
    with session_scope() as db:
        if isinstance(request, ThreadReply):
            parent = db.get(SlackThreadOpening, (instance_id, f"{request.run_id}:thread"))
            if not parent or parent.thread_ts != request.parent_ts:
                return ThreadReceipt(state="failed", reason="thread_mismatch")
            channel = parent.channel_id
        claimed = db.scalar(
            insert(SlackThreadOpening).values(
                instance_id=instance_id, operation_id=operation_id, request_digest=request_digest,
                channel_id=channel, started_at=utcnow(), state="sending",
                draft_version=request.draft.version if isinstance(request, ThreadReply) and request.draft else None,
            ).on_conflict_do_nothing().returning(SlackThreadOpening.operation_id)
        )
        row = db.get(SlackThreadOpening, key)
        assert row is not None
        if row.request_digest != request_digest:
            return ThreadReceipt(state="failed", reason="operation_mismatch")
        channel = row.channel_id

    if claimed:
        try:
            if isinstance(request, ThreadReply):
                ts = workshop_slack.post_reply(token, channel, request)
            else:
                ts = workshop_slack.post_root(token, channel, request.reporter_slack_user_id, request)
        except SlackRejected as exc:
            return _record_failure(key, "failed", str(exc))
        except (httpx.HTTPError, ValueError):
            return _record_failure(key, "unknown", "slack_post_unconfirmed")
        with session_scope() as db:
            stored = db.get(SlackThreadOpening, key)
            assert stored is not None
            stored.state, stored.thread_ts = "posted", ts
            row = stored

    if row.state == "sending":
        if utcnow() - row.started_at > POST_WINDOW:
            return ThreadReceipt(state="unknown", reason="slack_post_unconfirmed")
        return ThreadReceipt(state="pending")
    if row.state in ("unknown", "failed"):
        return ThreadReceipt(state=row.state, reason=row.reason)
    if row.thread_url:
        return ThreadReceipt(state="opened", channel_id=channel, thread_ts=row.thread_ts, thread_url=row.thread_url)

    ts = row.thread_ts
    assert ts is not None
    try:
        url = workshop_slack.permalink(token, channel, ts)
    except (SlackRejected, httpx.HTTPError, ValueError):
        return ThreadReceipt(state="pending", channel_id=channel, thread_ts=ts, reason="permalink_unavailable")
    with session_scope() as db:
        stored = db.get(SlackThreadOpening, key)
        assert stored is not None
        stored.thread_url = url
    return ThreadReceipt(state="opened", channel_id=channel, thread_ts=ts, thread_url=url)


def _record_failure(key: tuple[str, str], state, reason: str) -> ThreadReceipt:
    with session_scope() as db:
        row = db.get(SlackThreadOpening, key)
        assert row is not None
        row.state, row.reason = state, reason
    return ThreadReceipt(state=state, reason=reason)
