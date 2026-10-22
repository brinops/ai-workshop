"""Slack Incoming Webhook notifications (Block Kit). Payloads are redacted before sending."""

from __future__ import annotations

import httpx

from app.config import get_settings
from app.services.redaction import redact_obj

EMOJI = {"remediated": ":white_check_mark:", "needs_review": ":warning:", "failed": ":x:"}
HEADLINE = {
    "remediated": "AI remediation succeeded — CI is green",
    "needs_review": "AI remediation needs human review",
    "failed": "AI remediation failed",
}


def _short_diff(diff: str, max_lines: int = 25) -> str:
    lines = [ln for ln in diff.splitlines() if ln.startswith(("+", "-", "@@")) and not ln.startswith(("+++", "---"))]
    clipped = lines[:max_lines]
    if len(lines) > max_lines:
        clipped.append(f"… {len(lines) - max_lines} more lines")
    return "\n".join(clipped)[:2500]


def build_message(kind: str, task: dict, details: dict) -> dict:
    s = get_settings()
    dashboard = f"{s.public_url.rstrip('/')}/tasks/{task['id']}" if s.public_url else None
    title = f"{EMOJI.get(kind, '')} {HEADLINE.get(kind, kind)}"
    fields = [
        {"type": "mrkdwn", "text": f"*Repository*\n{task['repo']}"},
        {"type": "mrkdwn", "text": f"*Pull request*\n<{task['pr_url']}|#{task['pr_number']} {task['title'][:80]}>"},
        {"type": "mrkdwn", "text": f"*Classification*\n`{task.get('classification') or 'UNKNOWN'}`"},
        {"type": "mrkdwn", "text": f"*Validation*\n{details.get('validation', 'n/a')}"},
    ]
    blocks: list[dict] = [
        {"type": "header", "text": {"type": "plain_text", "text": title[:150], "emoji": True}},
        {"type": "section", "fields": fields},
    ]
    if details.get("problem"):
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*Original problem*\n{details['problem'][:600]}"}})
    if task.get("root_cause"):
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*Root cause*\n{task['root_cause'][:900]}"}})
    if details.get("files"):
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
                                                    "text": "*Files changed*\n" + "\n".join(f"• `{f}`" for f in details["files"][:10])}})
    if details.get("diff"):
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*Diff*\n```{_short_diff(details['diff'])}```"}})
    if details.get("reason"):
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*Why*\n{details['reason'][:900]}"}})
    links = [f"<{task['pr_url']}|Open PR on GitHub>"]
    if details.get("commit_url"):
        links.append(f"<{details['commit_url']}|Fix commit>")
    if dashboard:
        links.append(f"<{dashboard}|Dashboard task>")
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": " · ".join(links)}]})
    return redact_obj({"text": f"{HEADLINE.get(kind, kind)}: {task['repo']}#{task['pr_number']}", "blocks": blocks})


async def send(payload: dict) -> tuple[str, str | None]:
    """Returns (status, error) where status is sent | failed | skipped."""
    url = get_settings().slack_webhook_url
    if not url:
        return "skipped", "SLACK_WEBHOOK_URL is not configured"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
        if resp.status_code == 200 and resp.text.strip() == "ok":
            return "sent", None
        return "failed", f"HTTP {resp.status_code}: {resp.text[:200]}"
    except httpx.HTTPError as exc:
        return "failed", f"{type(exc).__name__}: {exc}"[:300]
