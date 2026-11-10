"""Receive local workshop events over Slack's outbound Socket Mode connection."""

import asyncio
import json
import logging
import re
from urllib.parse import urlsplit

import httpx
from sqlalchemy.exc import SQLAlchemyError
from websockets.asyncio.client import connect
from websockets.exceptions import WebSocketException

from app.services.slack_inbox import store_draft_action, store_thread_reply
from app.services.slack_routing import route_socket_event
from app.slack_router import consume_slack_event

log = logging.getLogger("rcp.slack_socket")


async def _connection_url(token: str) -> str:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post("https://slack.com/api/apps.connections.open",
                                     headers={"Authorization": f"Bearer {token}"})
        response.raise_for_status()
        data = response.json()
    if not isinstance(data, dict):
        raise ValueError("invalid Slack connection response")
    if data.get("ok") is not True:
        error = data.get("error", "")
        code = error if isinstance(error, str) and re.fullmatch(r"[a-z0-9_]{1,64}", error) else "unknown_error"
        log.warning("Slack rejected Socket Mode connection: %s", code)
        raise ValueError("Slack rejected Socket Mode connection")
    url = data.get("url")
    if not isinstance(url, str) or urlsplit(url).scheme != "wss":
        raise ValueError("Slack connection URL missing")
    return url


async def receive_events(socket, workspace: str, *, shared: bool = False) -> None:
    async for raw in socket:
        envelope = json.loads(raw)
        if not isinstance(envelope, dict):
            continue
        kind = envelope.get("type")
        if kind == "hello":
            log.info("Slack Socket Mode connected")
        if kind == "disconnect":
            return
        event_id = envelope.get("envelope_id")
        if not isinstance(event_id, str):
            continue
        payload = envelope.get("payload")
        if kind == "events_api" and isinstance(payload, dict):
            paired = await asyncio.to_thread(consume_slack_event, payload, workspace)
            if shared:
                stored = await asyncio.to_thread(route_socket_event, kind, payload, workspace)
            else:
                stored = await asyncio.to_thread(store_thread_reply, payload, workspace)
            event = payload.get("event")
            if isinstance(event, dict):
                log.info("Slack event received (type=%s, channel_type=%s, expected_workspace=%s, paired=%s, stored=%s)",
                         event.get("type"), event.get("channel_type"), payload.get("team_id") == workspace, paired, stored)
        elif kind == "interactive" and isinstance(payload, dict):
            if shared:
                stored = await asyncio.to_thread(route_socket_event, kind, payload, workspace)
            else:
                stored = await asyncio.to_thread(store_draft_action, payload, workspace)
            log.info("Slack interaction received (type=%s, stored=%s)", payload.get("type"), stored)
        await socket.send(json.dumps({"envelope_id": event_id}))


async def run_socket_mode(token: str, workspace: str, *, shared: bool = False) -> None:
    while True:
        try:
            url = await _connection_url(token)
            async with connect(url, open_timeout=10, close_timeout=2) as socket:
                await receive_events(socket, workspace, shared=shared)
        except (httpx.HTTPError, OSError, SQLAlchemyError, ValueError, WebSocketException) as exc:
            # Do not log errors containing the Slack WebSocket ticket or request.
            log.warning("Slack Socket Mode disconnected (%s); retrying", type(exc).__name__)
        await asyncio.sleep(3)
