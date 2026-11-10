"""Local API used by the workshop dashboard to pair a Slack account."""

from secrets import token_hex
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from app.config import get_settings
from app.db import session_scope
from app.models.slack_pairing import SlackPairing
from app.services.workshop_pairing import activate_training_profile, local_identity
from app.slack_router import PairingStatus, digest, status, store_pairing

router = APIRouter(prefix="/api/jira/workshop/pairing", tags=["Workshop pairing"])


class LocalPairingStatus(BaseModel):
    state: Literal["idle", "pending", "expired", "connected"]
    code: str | None = None
    workspace_id: str | None = None
    slack_user_id: str | None = None
    profile_id: str | None = None
    reporter_id: str | None = None


def router_request(url: str, identity: dict[str, str], code: str | None) -> PairingStatus | None:
    path = f"{url.rstrip('/')}/pairings/{identity['instance_id']}"
    headers = {"Authorization": f"Bearer {identity['token']}"}
    try:
        with httpx.Client(timeout=5, follow_redirects=False) as client:
            result = client.put(path, headers=headers, json={"code": code}) if code else client.get(path, headers=headers)
        if not code and result.status_code == 404:
            return None
        result.raise_for_status()
        return PairingStatus.model_validate(result.json())
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, "workshop Slack router unavailable or returned an invalid pairing response") from exc


def pairing(code: str | None) -> LocalPairingStatus:
    settings = get_settings()
    url = settings.workshop_slack_router_url
    socket_mode = bool(settings.workshop_slack_app_token)
    if socket_mode and not settings.workshop_slack_workspace_id:
        raise HTTPException(503, "workshop Slack workspace is not configured")
    if not socket_mode and not url:
        raise HTTPException(503, "workshop Slack router is not configured")
    with session_scope() as db:
        identity = local_identity(db, create=code is not None)
    if identity is None:
        return LocalPairingStatus(state="idle")
    if socket_mode:
        with session_scope() as db:
            instance_id = identity["instance_id"]
            row = (store_pairing(db, instance_id, digest(identity["token"]), code)
                   if code else db.get(SlackPairing, instance_id))
            remote = status(row) if row else None
    else:
        assert url is not None
        remote = router_request(url, identity, code)
    if remote is None:
        return LocalPairingStatus(state="idle")
    if remote.state != "connected":
        return LocalPairingStatus(state=remote.state, code=code if remote.state == "pending" else None)
    if not remote.workspace_id or not remote.slack_user_id:
        raise HTTPException(502, "confirmed pairing has no Slack identity")
    try:
        with session_scope() as db:
            profile = activate_training_profile(db, identity["instance_id"], remote.workspace_id, remote.slack_user_id)
    except ValueError as exc:
        raise HTTPException(409, "confirmed Slack identity differs from the local profile") from exc
    return LocalPairingStatus(
        state="connected", profile_id=profile.profile_id, reporter_id=profile.source_reporter_id,
        workspace_id=profile.slack_workspace_id, slack_user_id=profile.slack_user_id,
    )


@router.post("")
def start_pairing(response: Response) -> LocalPairingStatus:
    response.headers["Cache-Control"] = "no-store"
    return pairing(token_hex(8).upper())


@router.get("")
def pairing_status(response: Response) -> LocalPairingStatus:
    response.headers["Cache-Control"] = "no-store"
    return pairing(None)
