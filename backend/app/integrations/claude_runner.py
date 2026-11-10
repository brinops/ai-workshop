"""Headless Claude Code runner (`claude -p --output-format stream-json`).

* Least privilege: explicit `--tools` + `--allowed-tools`, `--permission-mode dontAsk`
  (anything not allowlisted is denied, never prompted, never bypassed).
* The process runs in its own process group with a wall-clock timeout and can be cancelled.
* The agent environment is scrubbed: no GitHub/Slack credentials are passed through.
* Agent definitions come from a trusted agent home (copied from the operator checkout),
  never from the PR worktree.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from app.config import REPO_ROOT, get_settings
from app.services.proc import terminate

log = logging.getLogger("rcp.claude")

# Environment variables an agent subprocess may inherit. Everything else is dropped.
_ENV_ALLOW = {
    "PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "TERM",
    "ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_BASE_URL", "ANTHROPIC_MODEL",
    "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "AWS_REGION", "AWS_PROFILE",
    "CLOUD_ML_REGION", "ANTHROPIC_VERTEX_PROJECT_ID", "XDG_CONFIG_HOME", "KUBECONFORM_CACHE",
    "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "SSL_CERT_FILE",
}


@dataclass
class AgentSpec:
    prompt: str
    tools: list[str]
    allowed_tools: list[str]
    json_schema: dict
    add_dirs: list[Path] = field(default_factory=list)
    agent: str | None = None
    timeout: float = 600
    model: str | None = None
    system_prompt_append: str | None = None
    cwd: Path | None = None
    output_language: str = "English"


@dataclass
class AgentResult:
    status: str  # succeeded | failed | timeout | cancelled
    structured: dict | None = None
    text: str = ""
    session_id: str | None = None
    model: str | None = None
    cost_usd: float | None = None
    num_turns: int | None = None
    exit_code: int | None = None
    error: str | None = None
    permission_denials: list = field(default_factory=list)


LogFn = Callable[..., None]  # emit(kind, summary, detail=None)
DETAIL_LIMIT = 20_000


def agent_env() -> dict[str, str]:
    s = get_settings()
    allow = _ENV_ALLOW | set(s.extra_env_passthrough)
    env = {k: v for k, v in os.environ.items() if k in allow}
    env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
    env["RCP_AGENT"] = "1"  # lets the PR-registration hook ignore agent sessions
    return env


def prepare_agent_home() -> Path:
    """Copy the trusted skills/agents from the operator checkout into a clean agent home."""
    home = get_settings().data_dir / "agent-home"
    dst = home / ".claude"
    for sub in ("skills", "agents"):
        src = REPO_ROOT / ".claude" / sub
        if (dst / sub).exists():
            shutil.rmtree(dst / sub)
        if src.exists():
            shutil.copytree(src, dst / sub)
    (dst / "settings.json").write_text(json.dumps({
        "permissions": {"deny": ["WebFetch", "WebSearch", "Bash(git push:*)", "Bash(gh:*)", "Bash(curl:*)"]},
    }, indent=2))
    return home


def build_command(spec: AgentSpec) -> list[str]:
    s = get_settings()
    cmd = [
        s.claude_path or s.claude_bin, "-p",
        "--output-format", "stream-json", "--verbose",
        "--permission-mode", "dontAsk",
        "--setting-sources", "project",
        "--no-session-persistence",
        "--model", spec.model or s.claude_model,
        "--max-budget-usd", f"{s.agent_max_budget_usd:.2f}",
        "--tools", ",".join(spec.tools),
        "--allowed-tools", *spec.allowed_tools,
        "--json-schema", json.dumps(spec.json_schema),
    ]
    for d in spec.add_dirs:
        cmd += ["--add-dir", str(d)]
    if spec.agent:
        cmd += ["--agent", spec.agent]
    # Agents run unattended for a machine consumer: pin the language and the result channel,
    # regardless of the operator's personal memory/preferences.
    append = (f"You are running headless inside the CI Control Plane. Write all prose in {spec.output_language}. "
              "Always finish by calling the StructuredOutput tool with your result.")
    if spec.system_prompt_append:
        append += "\n" + spec.system_prompt_append
    cmd += ["--append-system-prompt", append]
    return cmd


def _summarize_tool_input(name: str, data: dict) -> str:
    if name in ("Read", "Edit", "Write"):
        return str(data.get("file_path", ""))
    if name in ("Grep", "Glob"):
        return f"{data.get('pattern', '')} {data.get('path', '') or ''}".strip()
    if name == "Bash":
        return str(data.get("command", ""))[:300]
    if name == "Skill":
        return str(data.get("skill") or data.get("command") or data)
    return json.dumps(data)[:300]


def parse_event(evt: dict, emit: LogFn, state: dict) -> None:
    kind = evt.get("type")
    if kind == "system" and evt.get("subtype") == "init":
        state["session_id"] = evt.get("session_id")
        state["model"] = evt.get("model")
        emit("system", f"session started · model {evt.get('model')} · tools {', '.join(evt.get('tools') or [])}")
    elif kind == "assistant":
        for block in (evt.get("message") or {}).get("content") or []:
            if block.get("type") == "text" and block.get("text", "").strip():
                emit("text", block["text"].strip())
            elif block.get("type") == "tool_use":
                name = block.get("name", "?")
                detail = json.dumps(block.get("input") or {}, indent=2, ensure_ascii=False)[:DETAIL_LIMIT]
                if name == "StructuredOutput":
                    emit("tool_use", "StructuredOutput · returning structured result", detail)
                else:
                    emit("tool_use", f"{name} · {_summarize_tool_input(name, block.get('input') or {})}", detail)
    elif kind == "user":
        for block in (evt.get("message") or {}).get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                content = block.get("content")
                if isinstance(content, list):
                    content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
                full = str(content or "").strip()
                text = full.replace("\n", " ⏎ ")
                prefix = "error · " if block.get("is_error") else ""
                emit("tool_result", prefix + (text[:400] + ("…" if len(text) > 400 else "")),
                     full[:DETAIL_LIMIT] if len(text) > 400 or "\n" in full else None)
    elif kind == "result":
        state["result"] = evt
        cost = evt.get("total_cost_usd")
        summary = {k: evt.get(k) for k in ("subtype", "is_error", "num_turns", "duration_ms", "total_cost_usd",
                                           "permission_denials", "structured_output")}
        emit("result", f"{evt.get('subtype')} · {evt.get('num_turns')} turns · "
                       f"${cost:.4f}" if isinstance(cost, (int, float)) else f"{evt.get('subtype')}",
             json.dumps(summary, indent=2, ensure_ascii=False)[:DETAIL_LIMIT])


async def run_agent(
    spec: AgentSpec,
    emit: LogFn,
    cancel: asyncio.Event,
    on_start: Callable[[int], None] | None = None,
) -> AgentResult:
    home = spec.cwd if spec.cwd is not None else prepare_agent_home()
    cmd = build_command(spec)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=home,
        env=agent_env(),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
        limit=16 * 1024 * 1024,
    )
    if on_start:
        on_start(proc.pid)
    assert proc.stdin and proc.stdout and proc.stderr
    state: dict = {}
    stderr_tail: list[str] = []

    async def write_prompt() -> None:
        try:
            proc.stdin.write(spec.prompt.encode())
            await proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            proc.stdin.close()

    async def read_stdout() -> None:
        async for raw in proc.stdout:
            line = raw.decode(errors="replace").strip()
            if not line:
                continue
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                emit("stderr", line[:500])
                continue
            parse_event(evt, emit, state)

    async def read_stderr() -> None:
        async for raw in proc.stderr:
            line = raw.decode(errors="replace").rstrip()
            if line:
                stderr_tail.append(line)
                del stderr_tail[:-30]

    io = asyncio.gather(write_prompt(), read_stdout(), read_stderr(), proc.wait())
    cancel_wait = asyncio.ensure_future(cancel.wait())
    try:
        done, _ = await asyncio.wait({io, cancel_wait}, timeout=spec.timeout, return_when=asyncio.FIRST_COMPLETED)
    except asyncio.CancelledError:
        await terminate(proc)
        io.cancel()
        await asyncio.gather(io, return_exceptions=True)
        raise
    finally:
        cancel_wait.cancel()

    if io not in done:
        await terminate(proc)
        io.cancel()
        await asyncio.gather(io, return_exceptions=True)
        status = "cancelled" if cancel.is_set() else "timeout"
        emit("system", f"agent process {status}")
        return AgentResult(status=status, session_id=state.get("session_id"), model=state.get("model"),
                           exit_code=proc.returncode, error=f"agent {status}")

    try:
        await io
    except Exception:
        await terminate(proc)
        raise

    result = state.get("result") or {}
    structured = result.get("structured_output")
    ok = proc.returncode == 0 and not result.get("is_error") and isinstance(structured, dict)
    error = None
    if not ok:
        error = (result.get("result") or "\n".join(stderr_tail) or f"exit code {proc.returncode}")[-1500:]
    return AgentResult(
        status="succeeded" if ok else "failed",
        structured=structured if isinstance(structured, dict) else None,
        text=str(result.get("result") or ""),
        session_id=state.get("session_id"),
        model=state.get("model"),
        cost_usd=result.get("total_cost_usd"),
        num_turns=result.get("num_turns"),
        exit_code=proc.returncode,
        error=error,
        permission_denials=result.get("permission_denials") or [],
    )
