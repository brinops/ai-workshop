"""Secret redaction for anything persisted, streamed to the UI or sent to Slack."""

from __future__ import annotations

import os
import re

_PATTERNS = [
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"sk-ant-[A-Za-z0-9\-_]{20,}"),
    re.compile(r"xox[abposr]-[A-Za-z0-9-]{10,}"),
    re.compile(r"xapp-[A-Za-z0-9-]{10,}"),
    re.compile(r"https://hooks\.slack\.com/services/[A-Za-z0-9/]+"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)(authorization:\s*(?:bearer|token)\s+)[^\s'\"]+"),
    re.compile(r"""(?i)((?:[a-z0-9_-]+[_-])?(?:api[_-]?key|token|secret|password|passwd|authorization)['"]\s*:\s*['"])[^'"\r\n]+"""),
    re.compile(r"(?i)\b((?:api[_-]?key|token|secret|password|passwd)\s*[=:]\s*)['\"]?[^\s'\"]{6,}"),
]

_SECRET_ENV = ("GITHUB_TOKEN", "GH_TOKEN", "SLACK_WEBHOOK_URL", "ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN",
               "RCP_API_TOKEN", "GITHUB_WEBHOOK_SECRET")


def redact(text: str | None) -> str:
    if not text:
        return text or ""
    for name in _SECRET_ENV:
        value = os.environ.get(name)
        if value and len(value) >= 8:
            text = text.replace(value, "[REDACTED]")
    for pattern in _PATTERNS:
        if pattern.groups:
            text = pattern.sub(lambda m: m.group(1) + "[REDACTED]", text)
        else:
            text = pattern.sub("[REDACTED]", text)
    return text


def redact_obj(obj):
    if isinstance(obj, str):
        return redact(obj)
    if isinstance(obj, dict):
        return {k: redact_obj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_obj(v) for v in obj]
    return obj
