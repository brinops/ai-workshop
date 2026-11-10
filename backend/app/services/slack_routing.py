"""Route Socket Mode events to the instance that opened the Slack thread."""

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert

from app.db import session_scope
from app.models.slack_pairing import SlackPairing
from app.models.slack_thread import SlackRoutedEvent, SlackThreadOpening
from app.services.slack_inbox import parse_draft_action, parse_thread_reply, routed_event


def route_socket_event(kind: str, payload: dict, workspace: str) -> bool:
    parsed = parse_thread_reply(payload, workspace) if kind == "events_api" else parse_draft_action(payload, workspace)
    if parsed is None:
        return False
    event, channel, parent = parsed
    is_reply = event.event_type == "slack.thread_reply"
    suffix = ":thread" if is_reply else f":draft:{event.draft_id}"
    with session_scope() as db:
        receipt = db.scalar(
            select(SlackThreadOpening)
            .join(SlackPairing, SlackPairing.instance_id == SlackThreadOpening.instance_id)
            .where(
                SlackPairing.workspace_id == workspace, SlackPairing.slack_user_id == event.actor_slack_user_id,
                SlackThreadOpening.channel_id == channel,
                SlackThreadOpening.thread_ts == (parent if is_reply else event.message_ts),
                SlackThreadOpening.operation_id.endswith(suffix, autoescape=True),
            )
        )
        if receipt is None:
            return False
        instance_id = receipt.instance_id
        run_id = receipt.operation_id.removesuffix(suffix)
        if not is_reply:
            # Older receipts have no version metadata. Their local draft still validates it.
            if receipt.draft_version is not None and receipt.draft_version != event.draft_version:
                return False
            root = db.get(SlackThreadOpening, (instance_id, f"{run_id}:thread"))
            if root is None or root.channel_id != channel or not root.thread_ts:
                return False
            if parent is not None and parent != root.thread_ts:
                return False
            parent = root.thread_ts
        assert parent is not None
        routed = routed_event(event, run_id, workspace, channel, parent)
        return db.scalar(
            insert(SlackRoutedEvent).values(
                event_id=routed.event_id, instance_id=instance_id,
                payload=routed.model_dump(mode="json", exclude_none=True),
            ).on_conflict_do_nothing(index_elements=[SlackRoutedEvent.event_id]).returning(SlackRoutedEvent.id)
        ) is not None
