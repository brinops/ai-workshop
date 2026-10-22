"""Isolated git worktrees per task attempt, backed by one bare clone per repository.

Only this module commits and pushes. Pushes are fast-forward only (no force) to the PR head branch.
"""

from __future__ import annotations

import asyncio
import fnmatch
import shutil
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.services import proc


class GitError(RuntimeError):
    pass


@dataclass
class ChangedFile:
    path: str
    status: str  # A | M | D | R...
    added: int
    removed: int


def is_protected(branch: str) -> bool:
    return any(fnmatch.fnmatch(branch, pat) for pat in get_settings().protected_branches)


class WorktreeManager:
    _locks: dict[str, asyncio.Lock] = {}

    def __init__(self, data_dir: Path | None = None):
        self.data_dir = data_dir or get_settings().data_dir
        self.repos_dir = self.data_dir / "repos"
        self.worktrees_dir = self.data_dir / "worktrees"

    def _lock(self, repo: str) -> asyncio.Lock:
        return self._locks.setdefault(repo, asyncio.Lock())

    async def _git(self, *args: str, cwd: Path, timeout: float = 180) -> str:
        res = await proc.run(["git", *args], cwd=cwd, timeout=timeout)
        if not res.ok:
            raise GitError(f"git {' '.join(args[:3])}… failed: {(res.stderr or res.stdout).strip()[-600:]}")
        return res.stdout.strip()

    def bare_path(self, repo: str) -> Path:
        return self.repos_dir / (repo.replace("/", "__") + ".git")

    async def ensure_clone(self, repo: str) -> Path:
        bare = self.bare_path(repo)
        if not (bare / "HEAD").exists():
            self.repos_dir.mkdir(parents=True, exist_ok=True)
            url = get_settings().git_remote_template.format(repo=repo)
            await self._git("clone", "--bare", "--filter=blob:none", url, str(bare), cwd=self.repos_dir, timeout=300)
        return bare

    async def fetch_pr(self, repo: str, pr_number: int, head_branch: str, base_branch: str) -> Path:
        async with self._lock(repo):
            bare = await self.ensure_clone(repo)
            await self._git(
                "fetch", "--force", "origin",
                f"+refs/pull/{pr_number}/head:refs/rcp/pr-{pr_number}",
                f"+refs/heads/{base_branch}:refs/rcp/base-{pr_number}",
                cwd=bare, timeout=300,
            )
            # The head branch may live in a fork that cannot be pushed to — fetch only when present.
            await proc.run(["git", "fetch", "--force", "origin", f"+refs/heads/{head_branch}:refs/rcp/head-{pr_number}"],
                           cwd=bare, timeout=120)
            return bare

    async def create(self, repo: str, task_id: int, label: str, sha: str) -> Path:
        bare = self.bare_path(repo)
        path = self.worktrees_dir / f"task-{task_id}-{label}"
        await self.remove(repo, path)
        self.worktrees_dir.mkdir(parents=True, exist_ok=True)
        async with self._lock(repo):
            await self._git("worktree", "add", "--force", "--detach", str(path), sha, cwd=bare)
        head = await self._git("rev-parse", "HEAD", cwd=path)
        if head != sha:
            raise GitError(f"worktree HEAD {head} != expected {sha}")
        return path

    async def remove(self, repo: str, path: Path) -> None:
        bare = self.bare_path(repo)
        if path.exists() and (bare / "HEAD").exists():
            await proc.run(["git", "worktree", "remove", "--force", str(path)], cwd=bare)
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
        if (bare / "HEAD").exists():
            await proc.run(["git", "worktree", "prune"], cwd=bare)

    async def diff_against(self, worktree: Path, base_ref: str, head: str = "HEAD") -> str:
        return await self._git("diff", "--no-color", f"{base_ref}...{head}", cwd=worktree)

    async def working_changes(self, worktree: Path) -> tuple[str, list[ChangedFile]]:
        await self._git("add", "-A", cwd=worktree)
        diff = await self._git("diff", "--cached", "--no-color", "--unified=3", cwd=worktree)
        numstat = await self._git("diff", "--cached", "--numstat", cwd=worktree)
        status = await self._git("diff", "--cached", "--name-status", cwd=worktree)
        kinds = {line.split("\t")[-1]: line.split("\t")[0] for line in status.splitlines() if line}
        files = []
        for line in numstat.splitlines():
            added, removed, path = line.split("\t", 2)
            files.append(ChangedFile(path, kinds.get(path, "M"), int(added) if added.isdigit() else 0,
                                     int(removed) if removed.isdigit() else 0))
        return diff, files

    async def commit(self, worktree: Path, message: str) -> str:
        s = get_settings()
        await self._git("-c", f"user.name={s.git_author_name}", "-c", f"user.email={s.git_author_email}",
                        "commit", "--no-verify", "-m", message, cwd=worktree)
        return await self._git("rev-parse", "HEAD", cwd=worktree)

    async def push(self, worktree: Path, branch: str) -> None:
        """Fast-forward push of HEAD to the PR branch. Never forces, never touches protected branches."""
        if is_protected(branch):
            raise GitError(f"refusing to push to protected branch {branch!r}")
        await self._git("push", "--no-verify", "origin", f"HEAD:refs/heads/{branch}", cwd=worktree, timeout=180)
