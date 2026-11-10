"""Slack Web API client and the workshop thread contract."""

import json
import re
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.integrations.training_jira import JiraIssueRef


class OpenThread(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    run_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,128}$")
    issue_ref: JiraIssueRef
    issue_key: str = Field(pattern=r"^[A-Z0-9_]+-[0-9]+$", max_length=128)
    slack_workspace_id: str
    reporter_slack_user_id: str


class DraftMessage(BaseModel):
    draft_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,128}$")
    version: int = Field(ge=1)
    rendered_append: str = Field(min_length=1, max_length=12000)


class ThreadReply(OpenThread):
    parent_ts: str = Field(pattern=r"^\d+\.\d+$", max_length=64)
    reply_key: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    text: str = Field(min_length=1, max_length=3000)
    draft: DraftMessage | None = None

    @property
    def operation_id(self) -> str:
        if self.draft:
            return f"{self.run_id}:draft:{self.draft.draft_id}"
        return f"{self.run_id}:reply:{self.reply_key}"


class ThreadReceipt(BaseModel):
    state: Literal["pending", "opened", "unknown", "failed"]
    channel_id: str | None = None
    thread_ts: str | None = None
    thread_url: str | None = None
    reason: str | None = None


class SlackRejected(Exception):
    """Slack explicitly rejected the post."""


def _slack_call(token: str, method: str, *, json=None, params=None) -> dict:
    with httpx.Client(base_url="https://slack.com/api/", timeout=5) as client:
        response = client.request("POST" if json is not None else "GET", method, json=json, params=params,
                                  headers={"Authorization": f"Bearer {token}"})
    if response.status_code == 429:
        raise SlackRejected("rate_limited")
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict):
        raise ValueError("invalid Slack response")
    if body.get("ok") is False:
        code = body.get("error", "")
        raise SlackRejected(code if isinstance(code, str) and re.fullmatch(r"[a-z0-9_]{1,64}", code) else "slack_rejected")
    if body.get("ok") is not True:
        raise ValueError("invalid Slack response")
    return body


def post_root(token: str, channel: str, reporter: str, request: OpenThread) -> str:
    source = "Навчальна Jira" if request.issue_ref.kind == "training" else "Jira Cloud"
    return _post_message(token, channel, {
        "text": f"<@{reporter}>, відкриваю тред для задачі *{request.issue_key}* · {source}.",
    })


def post_reply(token: str, channel: str, request: ThreadReply) -> str:
    payload = {"thread_ts": request.parent_ts, "mrkdwn": False}
    if draft := request.draft:
        value = json.dumps({"draft_id": draft.draft_id, "draft_version": draft.version}, separators=(",", ":"))
        text = f"Чернетка v{draft.version}\n{draft.rendered_append}"
        fallback = f"{request.text}\n\n{text}"
        if len(fallback) <= 4000:
            payload["text"] = fallback
        sections = [request.text, *[text[i:i + 3000] for i in range(0, len(text), 3000)]]
        payload["blocks"] = [
            *[{"type": "section", "text": {"type": "plain_text", "text": section}} for section in sections],
            {"type": "actions", "elements": [
                {"type": "button", "text": {"type": "plain_text", "text": "Схвалити"},
                 "action_id": "approve", "value": value, "style": "primary"},
                {"type": "button", "text": {"type": "plain_text", "text": "Попросити правки"},
                 "action_id": "request_revision", "value": value},
            ]},
        ]
    else:
        payload["text"] = request.text
    return _post_message(token, channel, payload)


def _post_message(token: str, channel: str, payload: dict) -> str:
    body = _slack_call(token, "chat.postMessage", json={
        **payload, "channel": channel, "unfurl_links": False, "unfurl_media": False,
    })
    ts = body.get("ts")
    if body.get("channel") != channel or not isinstance(ts, str) or not re.fullmatch(r"\d+\.\d+", ts):
        raise ValueError("Slack post receipt is missing the expected channel or timestamp")
    return ts


def permalink(token: str, channel: str, ts: str) -> str:
    body = _slack_call(token, "chat.getPermalink", params={"channel": channel, "message_ts": ts})
    url = body.get("permalink")
    if not isinstance(url, str) or not url.startswith("https://"):
        raise ValueError("Slack permalink missing")
    return url
