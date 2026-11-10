"""Pull routed Slack events over the private network and acknowledge durable writes."""

import httpx
from pydantic import TypeAdapter

from app.db import session_scope
from app.services.slack_inbox import RoutedSlackEvent, local_route_matches, store_local_event
from app.services.workshop_pairing import active_profile_id, local_identity

BATCH = TypeAdapter(list[RoutedSlackEvent])


async def poll_slack_inbox(router_url: str) -> None:
    with session_scope() as db:
        identity = local_identity(db)
        if not identity or not active_profile_id(db):
            return
    path = f"{router_url.rstrip('/')}/pairings/{identity['instance_id']}/inbox"
    headers = {"Authorization": f"Bearer {identity['token']}"}
    async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
        response = await client.get(path, headers=headers)
        response.raise_for_status()
        events = BATCH.validate_json(response.content)
        acknowledged = []
        with session_scope() as db:
            for event in events:
                if local_route_matches(db, event):
                    store_local_event(db, event)
                    # A committed duplicate is safe to acknowledge after a lost ACK.
                    acknowledged.append(event.event_id)
        if acknowledged:
            response = await client.post(f"{path}/ack", headers=headers, json={"event_ids": acknowledged})
            response.raise_for_status()
