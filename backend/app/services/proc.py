"""Safe subprocess execution: argv lists only (no shell), timeouts, process-group kill."""

from __future__ import annotations

import asyncio
import os
import signal
from dataclasses import dataclass


@dataclass
class ProcResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out


def kill_group(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return


async def terminate(proc: asyncio.subprocess.Process, grace: float = 5.0) -> None:
    kill_group(proc)
    try:
        await asyncio.wait_for(proc.wait(), grace)
    except TimeoutError:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        await proc.wait()


async def run(
    argv: list[str],
    *,
    cwd: str | os.PathLike | None = None,
    timeout: float = 120,
    env: dict[str, str] | None = None,
    stdin: str | None = None,
) -> ProcResult:
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        env=env,
        stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(stdin.encode() if stdin is not None else None), timeout)
    except TimeoutError:
        await terminate(proc)
        return ProcResult(-1, "", f"timed out after {timeout}s", timed_out=True)
    except asyncio.CancelledError:
        await terminate(proc)
        raise
    return ProcResult(proc.returncode or 0, out.decode(errors="replace"), err.decode(errors="replace"))
