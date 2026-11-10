"""Shared Slack bot ingress and local workshop pairing API."""

import asyncio
import hashlib
import hmac
import json
import re
from contextlib import asynccontextmanager, suppress
from datetime import timedelta
from time import time
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.db import get_db, init_engine, run_migrations, session_scope, utcnow
from app.integrations.workshop_slack import OpenThread, ThreadReceipt, ThreadReply
from app.models.slack_pairing import SlackPairing
from app.models.slack_thread import SlackRoutedEvent
from app.services.slack_inbox import RoutedSlackEvent
from app.services.slack_threads import open_thread

CODE_PATTERN = r"[0-9A-F]{16}"
Database = Annotated[Session, Depends(get_db)]
Authorization = Annotated[str | None, Header()]


class StartPairing(BaseModel):
    code: str = Field(pattern=f"^{CODE_PATTERN}$")


class PairingStatus(BaseModel):
    state: Literal["pending", "expired", "connected"]
    workspace_id: str | None = None
    slack_user_id: str | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    run_migrations()
    init_engine()
    settings = get_settings()
    task = None
    if settings.workshop_slack_app_token and settings.workshop_slack_workspace_id:
        from app.integrations.slack_socket import run_socket_mode

        task = asyncio.create_task(run_socket_mode(
            settings.workshop_slack_app_token.get_secret_value(), settings.workshop_slack_workspace_id, shared=True,
        ), name="shared-workshop-slack-socket")
    try:
        yield
    finally:
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


app = FastAPI(title="Workshop Slack Router", lifespan=lifespan)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def token_digest(instance_id: str, authorization: str | None) -> str:
    token = (authorization or "").removeprefix("Bearer ")
    if not re.fullmatch(r"[0-9a-f]{32}", instance_id) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        raise HTTPException(401, "invalid pairing credentials")
    if not (authorization or "").startswith("Bearer "):
        raise HTTPException(401, "invalid pairing credentials")
    return digest(token)


def status(row: SlackPairing) -> PairingStatus:
    if row.slack_user_id:
        return PairingStatus(state="connected", workspace_id=row.workspace_id, slack_user_id=row.slack_user_id)
    return PairingStatus(state="pending" if row.expires_at > utcnow() else "expired")


def store_pairing(db: Session, instance_id: str, credential: str, code: str) -> SlackPairing:
    code_digest = digest(code)
    expires = utcnow() + timedelta(minutes=5)
    db.execute(
        insert(SlackPairing).values(
            instance_id=instance_id, token_digest=credential, code_digest=code_digest, expires_at=expires,
        ).on_conflict_do_update(
            index_elements=[SlackPairing.instance_id],
            set_={"code_digest": code_digest, "expires_at": expires},
            where=(SlackPairing.token_digest == credential) & SlackPairing.slack_user_id.is_(None),
        )
    )
    row = db.get(SlackPairing, instance_id)
    if row is None or not hmac.compare_digest(row.token_digest, credential):
        raise HTTPException(401, "invalid pairing credentials")
    return row


@app.put("/pairings/{instance_id}")
def start_pairing(instance_id: str, body: StartPairing, db: Database,
                  authorization: Authorization = None) -> PairingStatus:
    return status(store_pairing(db, instance_id, token_digest(instance_id, authorization), body.code))


@app.get("/pairings/{instance_id}")
def get_pairing(instance_id: str, db: Database, authorization: Authorization = None) -> PairingStatus:
    credential = token_digest(instance_id, authorization)
    row = db.get(SlackPairing, instance_id)
    if row is None:
        raise HTTPException(404, "pairing not started")
    if not hmac.compare_digest(row.token_digest, credential):
        raise HTTPException(401, "invalid pairing credentials")
    return status(row)


def _confirmed_pairing(db: Session, instance_id: str, authorization: str | None) -> SlackPairing:
    credential = token_digest(instance_id, authorization)
    row = db.get(SlackPairing, instance_id)
    if row is None or not hmac.compare_digest(row.token_digest, credential):
        raise HTTPException(401, "invalid pairing credentials")
    if not row.workspace_id or not row.slack_user_id:
        raise HTTPException(403, "Slack pairing is not confirmed")
    return row


class InboxAck(BaseModel):
    event_ids: list[Annotated[str, Field(min_length=1, max_length=255)]] = Field(min_length=1, max_length=50)


@app.get("/pairings/{instance_id}/inbox", response_model_exclude_none=True)
def get_inbox(instance_id: str, db: Database, authorization: Authorization = None) -> list[RoutedSlackEvent]:
    _confirmed_pairing(db, instance_id, authorization)
    events = db.scalars(
        select(SlackRoutedEvent).where(
            SlackRoutedEvent.instance_id == instance_id, SlackRoutedEvent.acknowledged_at.is_(None),
        ).order_by(SlackRoutedEvent.id).limit(50)
    )
    return [RoutedSlackEvent.model_validate(event.payload) for event in events]


@app.post("/pairings/{instance_id}/inbox/ack", status_code=204)
def acknowledge_inbox(instance_id: str, body: InboxAck, db: Database, authorization: Authorization = None) -> None:
    _confirmed_pairing(db, instance_id, authorization)
    db.execute(
        update(SlackRoutedEvent).where(
            SlackRoutedEvent.instance_id == instance_id, SlackRoutedEvent.event_id.in_(body.event_ids),
            SlackRoutedEvent.acknowledged_at.is_(None),
        ).values(acknowledged_at=utcnow())
    )


@app.put("/pairings/{instance_id}/threads/{operation_id}")
def open_paired_thread(instance_id: str, operation_id: str, body: ThreadReply | OpenThread,
                       authorization: Authorization = None) -> ThreadReceipt:
    with session_scope() as db:
        pairing = _confirmed_pairing(db, instance_id, authorization)
        if (pairing.workspace_id, pairing.slack_user_id) != (
            body.slack_workspace_id, body.reporter_slack_user_id,
        ):
            raise HTTPException(403, "Slack identity does not match the pairing")
    expected_id = body.operation_id if isinstance(body, ThreadReply) else f"{body.run_id}:thread"
    if operation_id != expected_id:
        raise HTTPException(400, "invalid thread operation ID")
    settings = get_settings()
    channel = settings.workshop_slack_channel_id
    token = settings.workshop_slack_bot_token
    if not channel or not token or settings.workshop_slack_workspace_id != body.slack_workspace_id:
        raise HTTPException(503, "workshop Slack posting is not configured")
    return open_thread(instance_id, operation_id, body, digest(body.model_dump_json()),
                       channel, token.get_secret_value())


def consume_slack_event(payload: dict, workspace: str) -> bool:
    """Pair a direct Slack message. The caller must authenticate the Slack envelope first."""
    event = payload.get("event")
    if payload.get("type") != "event_callback" or payload.get("team_id") != workspace or not isinstance(event, dict):
        return False
    if event.get("type") != "message" or event.get("channel_type") != "im" or event.get("subtype") or event.get("bot_id"):
        return False
    actor, text = event.get("user"), event.get("text")
    if not isinstance(actor, str) or not re.fullmatch(r"[UW][A-Z0-9]{1,63}", actor) or not isinstance(text, str):
        return False
    match = re.fullmatch(rf"(?:pair\s+)?({CODE_PATTERN})", text.strip(), flags=re.IGNORECASE)
    if not match:
        return False
    try:
        with session_scope() as db:
            result = db.execute(
                update(SlackPairing).where(
                    SlackPairing.code_digest == digest(match[1].upper()),
                    SlackPairing.expires_at > utcnow(),
                    SlackPairing.slack_user_id.is_(None),
                ).values(code_digest=None, workspace_id=workspace, slack_user_id=actor)
            )
            return result.rowcount == 1
    except IntegrityError:
        # A confirmed Slack identity is already bound to a different local instance.
        return False


@app.post("/slack/events")
async def slack_events(request: Request) -> dict:
    settings = get_settings()
    secret = settings.workshop_slack_signing_secret
    workspace = settings.workshop_slack_workspace_id
    if not secret or not workspace:
        raise HTTPException(503, "Slack ingress is not configured")
    body = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")
    if not re.fullmatch(r"[0-9]{1,12}", timestamp) or abs(time() - int(timestamp)) > 300:
        raise HTTPException(401, "invalid Slack signature")
    expected = "v0=" + hmac.new(secret.get_secret_value().encode(), b"v0:" + timestamp.encode() + b":" + body,
                                hashlib.sha256).hexdigest()
    if not re.fullmatch(r"v0=[0-9a-f]{64}", signature) or not hmac.compare_digest(expected, signature):
        raise HTTPException(401, "invalid Slack signature")
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeError) as exc:
        raise HTTPException(400, "invalid Slack payload") from exc
    if not isinstance(payload, dict):
        raise HTTPException(400, "invalid Slack payload")
    if payload.get("type") == "url_verification" and isinstance(payload.get("challenge"), str):
        return {"challenge": payload["challenge"]}
    return {"ok": True, "paired": await run_in_threadpool(consume_slack_event, payload, workspace)}
