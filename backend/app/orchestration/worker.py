"""Background worker: CI polling, stage dispatch, leases, heartbeats, cancellation and crash recovery.

The database is the single source of truth. A stage handler:
  1. claims the task with an atomic conditional UPDATE (lease = PR-level lock),
  2. does slow work outside any transaction (GitHub, git, Claude Code) while heartbeating the lease,
  3. re-reads the task and only commits its result if the task is still in the state it claimed
     (a user may have cancelled / marked for review in the meantime — stale results are discarded).
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import and_, or_, select, update

from app.agents import analysis as analysis_contract
from app.agents import remediation as remediation_contract
from app.config import get_settings
from app.control_plane import ControlPlaneConfig, Repository, Route, get_config
from app.db import session_scope, utcnow
from app.integrations import claude_runner, slack
from app.integrations.claude_runner import AgentResult, AgentSpec
from app.integrations.git_worktree import GitError, WorktreeManager
from app.integrations.github import GitHubClient, GitHubError
from app.models import (
    AgentLogLine,
    AgentRun,
    CISnapshot,
    Comment,
    Notification,
    PendingAction,
    Remediation,
    Task,
    TaskState,
    ValidationRun,
    WorkerHeartbeat,
)
from app.orchestration.ci import CIOverall, aggregate, extract_findings, log_excerpt
from app.orchestration.state_machine import transition
from app.services import validation as local_validation
from app.services.events import add_comment, record_event
from app.services.redaction import redact
from app.services.registration import retarget_to_head
from app.services.settings_store import get_automation

log = logging.getLogger("rcp.worker")

S = TaskState
AgentFn = Callable[..., Awaitable[AgentResult]]


@dataclass
class Deps:
    github: Callable[[], GitHubClient] = GitHubClient
    worktrees: WorktreeManager = field(default_factory=WorktreeManager)
    run_agent: AgentFn = claude_runner.run_agent
    validate: Callable[[Path, Route], Awaitable[dict]] = local_validation.validate
    config: Callable[[], ControlPlaneConfig] = get_config
    slack_send: Callable[[dict], Awaitable[tuple[str, str | None]]] = slack.send


@dataclass
class Running:
    task_id: int
    stage: S
    cancel: asyncio.Event
    job: asyncio.Task | None = None


class StageAborted(Exception):
    """The task left the claimed state while the stage was running (cancel / review / new commit)."""


class Worker:
    def __init__(self, deps: Deps | None = None, worker_id: str | None = None):
        self.deps = deps or Deps()
        self.settings = get_settings()
        self.id = worker_id or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
        self.running: dict[int, Running] = {}
        self._stop = asyncio.Event()
        self._gh: GitHubClient | None = None

    # ------------------------------------------------------------------ lifecycle
    @property
    def gh(self) -> GitHubClient:
        if self._gh is None:
            self._gh = self.deps.github()
        return self._gh

    async def run_forever(self) -> None:
        log.info("worker %s started", self.id)
        with session_scope() as db:
            db.merge(WorkerHeartbeat(worker_id=self.id, ts=utcnow(), started_at=utcnow(), info={"pid": os.getpid()}))
            record_event(db, None, "worker_started", f"Worker {self.id} started")
        self.recover(startup=True)
        while not self._stop.is_set():
            try:
                await self.tick()
            except Exception:  # never let the loop die
                log.exception("worker tick failed")
            try:
                await asyncio.wait_for(self._stop.wait(), self.settings.worker_tick_seconds)
            except TimeoutError:
                pass
        await self.shutdown()

    def stop(self) -> None:
        self._stop.set()

    async def shutdown(self) -> None:
        """Graceful shutdown: stop agents, mark runs interrupted, release leases so a restart resumes at once."""
        for r in list(self.running.values()):
            r.cancel.set()
        jobs = [r.job for r in self.running.values() if r.job]
        if jobs:
            await asyncio.gather(*jobs, return_exceptions=True)
        with session_scope() as db:
            db.execute(update(Task).where(Task.lease_owner == self.id).values(lease_owner=None, lease_expires_at=None))
            db.execute(update(AgentRun).where(AgentRun.worker_id == self.id, AgentRun.status == "running")
                       .values(status="interrupted", finished_at=utcnow(), error="worker shut down"))
            hb = db.get(WorkerHeartbeat, self.id)
            if hb:
                db.delete(hb)
            record_event(db, None, "worker_stopped", f"Worker {self.id} stopped")
        if self._gh:
            self._gh.close()
        log.info("worker %s stopped", self.id)

    # ------------------------------------------------------------------ tick
    async def tick(self) -> None:
        with session_scope() as db:
            hb = db.get(WorkerHeartbeat, self.id)
            if hb:
                hb.ts = utcnow()
                hb.info = {"pid": os.getpid(), "running": sorted(self.running)}
        self.recover()
        self.watch_running()
        await self.poll_due_ci()
        self.dispatch()

    def recover(self, startup: bool = False) -> None:
        """Release expired leases left by a dead worker and mark its agent runs as interrupted."""
        now = utcnow()
        with session_scope() as db:
            stale = db.scalars(select(Task).where(Task.lease_owner.is_not(None), Task.lease_expires_at < now)).all()
            for t in stale:
                runs = db.scalars(select(AgentRun).where(AgentRun.task_id == t.id, AgentRun.status == "running")).all()
                for run in runs:
                    run.status, run.finished_at, run.error = "interrupted", now, f"lease of {t.lease_owner} expired"
                record_event(db, t.id, "recovered",
                             f"Recovered {t.state} after interrupted execution (worker {t.lease_owner} lost its lease)",
                             level="warning", data={"previous_owner": t.lease_owner})
                t.lease_owner = t.lease_expires_at = None
                t.cancel_requested = False
                t.activity = None
            if startup:
                orphans = db.scalars(select(AgentRun).where(AgentRun.status == "running")).all()
                for run in orphans:
                    task = db.get(Task, run.task_id)
                    if task is None or task.lease_owner is None:
                        run.status, run.finished_at, run.error = "interrupted", now, "control plane restarted"

    def watch_running(self) -> None:
        """Signal cancellation to running stages whose task was cancelled, re-routed or no longer leased by us."""
        if not self.running:
            return
        with session_scope() as db:
            for r in self.running.values():
                t = db.get(Task, r.task_id)
                if t is None or t.cancel_requested or t.state != r.stage or t.lease_owner != self.id:
                    r.cancel.set()

    # ------------------------------------------------------------------ claiming
    def claim(self, task_id: int, state: S, seconds: int | None = None) -> bool:
        now = utcnow()
        lease = now + timedelta(seconds=seconds or self.settings.lease_seconds)
        with session_scope() as db:
            res = db.execute(
                update(Task)
                .where(
                    Task.id == task_id,
                    Task.state == state,
                    Task.paused.is_(False),
                    Task.cancel_requested.is_(False),
                    or_(Task.lease_owner.is_(None), Task.lease_expires_at < now),
                )
                .values(lease_owner=self.id, lease_expires_at=lease)
            )
            return res.rowcount == 1

    def release(self, task_id: int) -> None:
        with session_scope() as db:
            db.execute(update(Task).where(Task.id == task_id, Task.lease_owner == self.id)
                       .values(lease_owner=None, lease_expires_at=None, cancel_requested=False))

    async def _heartbeat(self, task_id: int) -> None:
        while True:
            await asyncio.sleep(self.settings.heartbeat_seconds)
            with session_scope() as db:
                db.execute(update(Task).where(Task.id == task_id, Task.lease_owner == self.id)
                           .values(lease_expires_at=utcnow() + timedelta(seconds=self.settings.lease_seconds)))

    def _owned(self, db, task_id: int, state: S) -> Task:
        """Re-read a task inside a write transaction; abort the stage if we no longer own it in `state`."""
        t = db.get(Task, task_id)
        if t is None or t.state != state or t.lease_owner != self.id or t.cancel_requested:
            raise StageAborted(f"task {task_id} left {state}")
        return t

    def set_activity(self, task_id: int, text: str | None) -> None:
        with session_scope() as db:
            t = db.get(Task, task_id)
            if t:
                t.activity = text

    # ------------------------------------------------------------------ CI polling
    async def poll_due_ci(self) -> None:
        now = utcnow()
        with session_scope() as db:
            due = db.scalars(
                select(Task.id).where(
                    Task.state.in_([S.WAITING_CI, S.VALIDATING]),
                    Task.paused.is_(False),
                    or_(Task.ci_next_check_at.is_(None), Task.ci_next_check_at <= now),
                    or_(Task.lease_owner.is_(None), Task.lease_expires_at < now),
                    # A failed PR waiting for "Analyze Now" does not need polling.
                    or_(Task.pending_action.is_(None), Task.pending_action != PendingAction.ANALYZE),
                )
            ).all()
        for task_id in due:
            try:
                await self.poll_ci(task_id)
            except Exception as exc:
                log.exception("CI poll failed for task %s", task_id)
                with session_scope() as db:
                    t = db.get(Task, task_id)
                    if t:
                        t.ci_next_check_at = utcnow() + timedelta(seconds=self.settings.ci_poll_interval_seconds * 2)
                        t.last_error = redact(str(exc))[:1000]
                        record_event(db, task_id, "ci_poll_error", f"GitHub status check failed: {exc}", level="warning")
        if due:
            await self.flush_notifications()

    async def poll_ci(self, task_id: int) -> None:
        with session_scope() as db:
            t = db.get(Task, task_id)
            if t is None:
                return
            repo, sha, state = t.repo, t.expected_sha, S(t.state)
            repo_cfg = self.deps.config().repository(repo)
            if repo_cfg is None:
                self._unconfigured(db, t)
                return
        runs = await asyncio.to_thread(self.gh.list_check_runs, repo, sha)
        result = aggregate(runs, repo_cfg.required_checks)
        auto = None
        with session_scope() as db:
            t = db.get(Task, task_id)
            if t is None or t.state != state or t.expected_sha != sha or t.paused:
                return
            auto = get_automation(db)
            now = utcnow()
            t.ci_checked_at = now
            t.ci_next_check_at = now + timedelta(seconds=self.settings.ci_poll_interval_seconds)
            last = db.scalar(select(CISnapshot).where(CISnapshot.task_id == task_id, CISnapshot.sha == sha)
                             .order_by(CISnapshot.id.desc()).limit(1))
            signature = [(c["name"], c["verdict"]) for c in result.required + result.others]
            if last is None or last.overall != result.overall or \
                    [(c["name"], c["verdict"]) for c in last.checks] != signature:
                db.add(CISnapshot(task_id=task_id, sha=sha, overall=result.overall, checks=result.required + result.others))
                summary = ", ".join(f"{c['name']}={c['verdict']}" for c in result.required) or "no checks yet"
                record_event(db, task_id, "ci_status", f"CI on {sha[:7]}: {result.overall} ({summary})",
                             level={"failure": "error", "success": "success"}.get(result.overall, "info"),
                             data={"sha": sha, "overall": result.overall,
                                   "checks": [{k: c.get(k) for k in ("name", "verdict", "conclusion", "html_url")}
                                              for c in result.required + result.others]})
            t.ci_status = result.overall

            if result.overall == CIOverall.PENDING:
                waited = (now - (t.ci_waiting_since or now)).total_seconds()
                if waited > self.settings.ci_wait_timeout_seconds:
                    reason = f"no conclusive result for required checks {repo_cfg.required_checks} after {int(waited)}s"
                    transition(db, t, S.NEEDS_REVIEW, reason, level="warning")
                    t.resolution = "ci_timeout"
                    self._queue_notification(db, t, "needs_review", reason)
                else:
                    pending = [c["name"] for c in result.required if c["verdict"] in ("pending", "missing")]
                    t.activity = f"Waiting for GitHub Actions: {', '.join(pending) or 'checks'} on {sha[:7]}"
                return

            if result.overall == CIOverall.SUCCESS:
                if state == S.WAITING_CI:
                    transition(db, t, S.DONE, "all required checks passed — no remediation needed", level="success")
                    t.resolution = "passed_without_remediation"
                else:
                    transition(db, t, S.DONE, f"required checks passed on remediation commit {sha[:7]}", level="success")
                    t.resolution = "remediated"
                    self._queue_notification(db, t, "remediated", None)
                return

            if result.overall in (CIOverall.CANCELLED, CIOverall.SKIPPED):
                reason = f"required checks were {result.overall} on {sha[:7]} — cannot prove validity"
                transition(db, t, S.NEEDS_REVIEW, reason, level="warning")
                t.resolution = f"ci_{result.overall}"
                self._queue_notification(db, t, "needs_review", reason)
                return

            # FAILURE — the failed check selects the route (skill, agent, validator, allowed paths).
            failed = next(c["name"] for c in result.failed_runs)
            route = repo_cfg.route(failed)
            if t.route != route.check:
                t.route = route.check
                t.max_attempts = route.max_attempts
                record_event(db, task_id, "route_selected",
                             f"Route {route.check} → skill {route.analysis_skill}, agent {route.remediation_agent}",
                             data=route.model_dump())
            if state == S.VALIDATING:
                if t.attempt >= t.max_attempts:
                    reason = f"remediation commit {sha[:7]} still fails CI and {t.attempt}/{t.max_attempts} attempts are used"
                    transition(db, t, S.NEEDS_REVIEW, reason, level="error")
                    t.resolution = "attempts_exhausted"
                    self._queue_notification(db, t, "needs_review", reason)
                    return
                t.analysis_runs = 0
                transition(db, t, S.ANALYZING,
                           f"remediation commit failed CI — re-analyzing (attempt {t.attempt + 1}/{t.max_attempts})",
                           level="warning")
                return
            if auto.auto_analyze:
                t.analysis_runs = 0
                transition(db, t, S.ANALYZING, "required check failed — Auto Analyze is on", level="error")
            elif t.pending_action != PendingAction.ANALYZE:
                t.pending_action = PendingAction.ANALYZE
                t.activity = "CI failed — waiting for “Analyze Now”"
                record_event(db, task_id, "awaiting_approval", "CI failed. Auto Analyze is off — waiting for “Analyze Now”",
                             level="warning")

    def _unconfigured(self, db, t: Task) -> None:
        reason = f"repository {t.repo} is not configured in control-plane.yaml"
        if t.state != S.NEEDS_REVIEW and t.state in (S.WAITING_CI, S.VALIDATING, S.ANALYZING, S.TODO, S.IN_PROGRESS):
            transition(db, t, S.NEEDS_REVIEW, reason, level="warning")
            t.resolution = "not_configured"

    def _route_or_review(self, db, t: Task) -> tuple[Repository, Route] | None:
        """The task's route from control-plane.yaml; a task without one goes to NEEDS_REVIEW (never guessed)."""
        repo_cfg = self.deps.config().repository(t.repo)
        route = repo_cfg.route(t.route) if repo_cfg else None
        if repo_cfg is None or route is None:
            reason = (f"no route for check {t.route!r} of {t.repo} in control-plane.yaml"
                      if repo_cfg else f"repository {t.repo} is not configured in control-plane.yaml")
            transition(db, t, S.NEEDS_REVIEW, reason, level="warning")
            t.resolution = "not_configured"
            return None
        return repo_cfg, route

    # ------------------------------------------------------------------ dispatch
    def dispatch(self) -> None:
        now = utcnow()
        free = self.settings.max_concurrent_agents - len(self.running)
        with session_scope() as db:
            auto = get_automation(db)
            candidates = db.scalars(
                select(Task).where(
                    Task.state.in_([S.ANALYZING, S.TODO, S.IN_PROGRESS]),
                    Task.paused.is_(False),
                    Task.cancel_requested.is_(False),
                    or_(Task.lease_owner.is_(None), Task.lease_expires_at < now),
                ).order_by(Task.updated_at)
            ).all()
            todo_ready = []
            for t in candidates:
                if t.state == S.TODO:
                    if auto.auto_remediate:
                        todo_ready.append(t.id)
                    elif t.pending_action != PendingAction.REMEDIATE:
                        t.pending_action = PendingAction.REMEDIATE
                        t.activity = "Diagnosis ready — waiting for “Start Remediation”"
                        record_event(db, t.id, "awaiting_approval",
                                     "Auto Remediate is off — waiting for “Start Remediation”", level="warning")
            for tid in todo_ready:
                t = db.get(Task, tid)
                start_remediation(db, t, "Auto Remediate is on")
            work = [(t.id, S(t.state)) for t in candidates if t.state in (S.ANALYZING, S.IN_PROGRESS)]
            work += [(tid, S.IN_PROGRESS) for tid in todo_ready]

        for task_id, state in work:
            if free <= 0 or task_id in self.running:
                continue
            if state == S.IN_PROGRESS and not self._in_progress_needs_work(task_id, auto.auto_push):
                continue
            if not self.claim(task_id, state):
                continue
            free -= 1
            r = Running(task_id, state, asyncio.Event())
            handler = self.run_analysis if state == S.ANALYZING else self.run_in_progress
            r.job = asyncio.create_task(self._run_stage(r, handler), name=f"task-{task_id}-{state}")
            self.running[task_id] = r

    def _in_progress_needs_work(self, task_id: int, auto_push: bool) -> bool:
        with session_scope() as db:
            t = db.get(Task, task_id)
            rem = latest_remediation(db, task_id, t.attempt) if t else None
            if t is None:
                return False
            if rem is None or rem.push_status in ("approved", "pushed"):
                return True
            if rem.push_status == "pending_approval":
                if auto_push:
                    return True
                if t.pending_action != PendingAction.PUSH:
                    t.pending_action = PendingAction.PUSH
                    t.activity = "Fix validated locally — waiting for “Approve Push”"
                    record_event(db, task_id, "awaiting_approval",
                                 "Auto Push is off — waiting for “Approve Push”", level="warning")
                return False
            return False

    async def _run_stage(self, r: Running, handler) -> None:
        hb = asyncio.create_task(self._heartbeat(r.task_id))
        try:
            await handler(r)
        except StageAborted as exc:
            log.info("stage aborted: %s", exc)
            with session_scope() as db:
                record_event(db, r.task_id, "stage_aborted", f"{r.stage} stage stopped: task was cancelled or re-routed",
                             level="warning")
        except Exception as exc:
            log.exception("stage %s failed for task %s", r.stage, r.task_id)
            with session_scope() as db:
                t = db.get(Task, r.task_id)
                if t is not None and t.state == r.stage and t.lease_owner == self.id:
                    t.last_error = redact(f"{type(exc).__name__}: {exc}")[:2000]
                    transition(db, t, S.FAILED, f"{r.stage} stage crashed: {type(exc).__name__}: {exc}"[:500], level="error")
                    t.resolution = "internal_error"
                    self._queue_notification(db, t, "failed", t.last_error)
        finally:
            hb.cancel()
            self.release(r.task_id)
            self.set_activity_if_idle(r.task_id)
            self.running.pop(r.task_id, None)
            await self.flush_notifications()

    def set_activity_if_idle(self, task_id: int) -> None:
        with session_scope() as db:
            t = db.get(Task, task_id)
            if t and t.state in (S.DONE, S.FAILED, S.NEEDS_REVIEW):
                t.activity = None

    # ------------------------------------------------------------------ agent bookkeeping
    def _start_run(self, task_id: int, kind: str, attempt: int) -> int:
        with session_scope() as db:
            run = AgentRun(task_id=task_id, kind=kind, attempt=attempt, status="running", worker_id=self.id,
                           model=self.settings.claude_model)
            db.add(run)
            db.flush()
            record_event(db, task_id, "agent_started", f"{kind.capitalize()} agent started (run #{run.id})",
                         data={"run_id": run.id, "kind": kind})
            return run.id

    def _emitter(self, run_id: int, task_id: int):
        def emit(kind: str, text: str, detail: str | None = None) -> None:
            with session_scope() as db:
                db.add(AgentLogLine(run_id=run_id, task_id=task_id, kind=kind, text=redact(text)[:4000],
                                    detail=redact(detail)[:20000] if detail else None))
        return emit

    def _set_pid(self, run_id: int):
        def on_start(pid: int) -> None:
            with session_scope() as db:
                run = db.get(AgentRun, run_id)
                if run:
                    run.pid = pid
        return on_start

    def _finish_run(self, run_id: int, res: AgentResult, status: str | None = None, error: str | None = None) -> None:
        with session_scope() as db:
            run = db.get(AgentRun, run_id)
            if run is None:
                return
            run.status = status or res.status
            run.finished_at = utcnow()
            run.exit_code, run.session_id = res.exit_code, res.session_id
            run.cost_usd, run.num_turns = res.cost_usd, res.num_turns
            run.model = res.model or run.model
            run.output = res.structured
            run.error = redact(error or res.error or "")[:4000] or None
            level = "success" if run.status == "succeeded" else "error"
            record_event(db, run.task_id, "agent_finished",
                         f"{run.kind.capitalize()} agent {run.status}"
                         + (f" · {res.num_turns} turns" if res.num_turns else "")
                         + (f" · ${res.cost_usd:.3f}" if res.cost_usd else ""),
                         level=level, data={"run_id": run_id, "status": run.status, "model": run.model,
                                            "turns": res.num_turns, "cost_usd": res.cost_usd,
                                            "session_id": res.session_id, "error": run.error,
                                            "permission_denials": res.permission_denials or None})

    # ------------------------------------------------------------------ ANALYZING
    async def run_analysis(self, r: Running) -> None:
        tid = r.task_id
        with session_scope() as db:
            t = self._owned(db, tid, S.ANALYZING)
            resolved = self._route_or_review(db, t)
            if resolved is None:
                return
            repo_cfg, route = resolved
            t.analysis_runs += 1
            t.activity = "Collecting evidence: CI logs, diff, local validation"
            snap = _snapshot(t)
        run_id = self._start_run(tid, "analysis", snap["attempt"])
        emit = self._emitter(run_id, tid)

        evidence = await self._collect_evidence(tid, snap, run_id, emit, repo_cfg, route)
        worktree, bundle = evidence["worktree"], evidence["bundle"]
        self._check_alive(r)

        self.set_activity(tid, f"Analysis Skill {route.analysis_skill} is investigating the failure")
        spec = AgentSpec(
            prompt=analysis_contract.build_prompt(bundle, worktree, route.analysis_skill),
            tools=["Read", "Grep", "Glob", "Skill"],
            allowed_tools=["Read", "Grep", "Glob", "Skill"],
            json_schema=analysis_contract.output_json_schema(),
            add_dirs=[bundle, worktree],
            timeout=self.settings.analysis_timeout_seconds,
        )
        res = await self.deps.run_agent(spec, emit, r.cancel, self._set_pid(run_id))
        await self.deps.worktrees.remove(snap["repo"], worktree)

        output, error = None, None
        if res.status == "succeeded":
            try:
                output = analysis_contract.AnalysisOutput.model_validate(res.structured)
            except ValidationError as exc:
                error = f"analysis output failed schema validation: {exc}"
        self._finish_run(run_id, res, status="failed" if error else None, error=error)
        if res.status == "cancelled":
            raise StageAborted("analysis cancelled")

        with session_scope() as db:
            t = self._owned(db, tid, S.ANALYZING)
            if output is None:
                reason = error or res.error or res.status
                if t.analysis_runs < self.settings.analysis_max_runs:
                    record_event(db, tid, "analysis_retry",
                                 f"Analysis run failed ({reason[:200]}); retrying "
                                 f"({t.analysis_runs}/{self.settings.analysis_max_runs})", level="warning")
                    return
                t.last_error = redact(reason)[:2000]
                transition(db, t, S.FAILED, f"analysis failed after {t.analysis_runs} runs: {reason[:300]}", level="error")
                t.resolution = "analysis_failed"
                self._queue_notification(db, t, "failed", reason)
                return

            findings = evidence["findings"]
            rec = analysis_contract.reconcile(output, findings, route)
            t.classification, t.confidence, t.root_cause = rec.classification, output.confidence, output.root_cause
            add_comment(db, tid, "analysis-skill", "diagnosis",
                        analysis_contract.render_markdown(output, rec, findings),
                        data={"analysis": output.model_dump(mode="json"), "reconciled": rec.model_dump(mode="json"),
                              "findings": findings, "findings_source": evidence["findings_source"],
                              "bundle_dir": str(bundle), "route": route.check,
                              "sha": snap["expected_sha"], "run_id": run_id})
            if rec.deterministic_classification and not rec.agreement:
                record_event(db, tid, "classification_overridden",
                             f"LLM said {rec.llm_classification}; deterministic evidence says "
                             f"{rec.deterministic_classification} — using deterministic", level="warning")
            if t.head_sha != t.expected_sha:
                retarget_to_head(db, t, "PR head moved during analysis")
                return
            if rec.remediable:
                transition(db, t, S.TODO, f"diagnosed {rec.classification} ({output.confidence:.0%}) — fix planned",
                           data={"classification": rec.classification})
            else:
                transition(db, t, S.NEEDS_REVIEW, f"{rec.classification}: {rec.decision_reason}"[:500], level="warning")
                t.resolution = "not_auto_remediable"
                self._queue_notification(db, t, "needs_review", rec.decision_reason)

    async def _collect_evidence(self, tid: int, snap: dict, run_id: int, emit, repo_cfg: Repository, route: Route) -> dict:
        repo, number, sha = snap["repo"], snap["pr_number"], snap["expected_sha"]
        emit("system", f"collecting evidence for {repo}#{number} @ {sha[:7]}")
        runs = await asyncio.to_thread(self.gh.list_check_runs, repo, sha)
        ci = aggregate(runs, repo_cfg.required_checks)
        logs, ci_findings, failed = [], [], []
        for c in ci.failed_runs:
            entry = {"name": c["name"], "conclusion": c.get("conclusion"), "url": c.get("html_url")}
            try:
                raw = await asyncio.to_thread(self.gh.get_job_log, repo, c["id"])
                ci_findings += extract_findings(raw)
                logs.append(f"===== {c['name']} ({c.get('conclusion')}) =====\n{log_excerpt(raw)}")
                entry["annotations"] = [
                    {k: a.get(k) for k in ("path", "start_line", "title", "message", "annotation_level")}
                    for a in await asyncio.to_thread(self.gh.get_annotations, repo, c["id"])
                ][:20]
            except GitHubError as exc:
                logs.append(f"===== {c['name']} — log unavailable: {exc} =====")
            failed.append(entry)
        emit("system", f"CI evidence: {len(failed)} failed check(s), {len(ci_findings)} deterministic finding(s)")

        files = await asyncio.to_thread(self.gh.get_pr_files, repo, number)
        await self.deps.worktrees.fetch_pr(repo, number, snap["head_branch"], snap["base_branch"])
        worktree = await self.deps.worktrees.create(repo, tid, f"analysis-r{run_id}", sha)
        diff = await self.deps.worktrees.diff_against(worktree, f"refs/rcp/base-{number}", sha)
        report = await self.deps.validate(worktree, route)
        local_findings = local_validation.findings_of(report)
        with session_scope() as db:
            db.add(ValidationRun(task_id=tid, sha=sha, purpose="pre-analysis", valid=bool(report.get("valid")),
                                 exit_code=report.get("exit_code", -1), report=report))
            record_event(db, tid, "local_validation",
                         f"Local validation of {sha[:7]}: {'valid' if report.get('valid') else f'{len(local_findings)} finding(s)'}",
                         level="info" if report.get("valid") else "warning",
                         data={"sha": sha, "validator": route.validator, "targets": route.scan_roots,
                               "valid": bool(report.get("valid")),
                               "findings": [{k: f.get(k) for k in ("category", "check", "file", "line", "message")}
                                            for f in local_findings]})
        emit("system", f"local validation ({route.validator}) on {', '.join(route.scan_roots)}: "
                       f"{'valid' if report.get('valid') else str(len(local_findings)) + ' finding(s)'}")

        findings, source = (ci_findings, "ci") if ci_findings else (
            [f for f in local_findings if f.get("category") != "TOOL_ERROR"], "local")
        context = {
            "pull_request": {"repo": repo, "number": number, "title": snap["title"], "author": snap["author"],
                             "head_branch": snap["head_branch"], "base_branch": snap["base_branch"], "head_sha": sha,
                             "url": snap["pr_url"]},
            "changed_files": files,
            "route": route.model_dump(),
            "failed_checks": failed,
            "deterministic_findings": findings,
            "deterministic_findings_source": source,
            "previous_attempts": snap["attempt"],
            "remediation_scope": route.allowed_paths,
            "worktree": str(worktree),
        }
        bundle = self.settings.data_dir / "runs" / f"task-{tid}" / f"analysis-{run_id}"
        analysis_contract.write_bundle(bundle, context, redact("\n\n".join(logs)), diff, report)
        return {"worktree": worktree, "bundle": bundle, "findings": findings, "findings_source": source}

    def _check_alive(self, r: Running) -> None:
        if r.cancel.is_set():
            raise StageAborted("cancelled")

    # ------------------------------------------------------------------ IN_PROGRESS
    async def run_in_progress(self, r: Running) -> None:
        with session_scope() as db:
            t = self._owned(db, r.task_id, S.IN_PROGRESS)
            rem = latest_remediation(db, t.id, t.attempt)
            auto_push = get_automation(db).auto_push
            status = rem.push_status if rem else None
        if status is None:
            pushed_now = await self.run_remediation(r, auto_push)
            if not pushed_now:
                return
        elif status in ("approved", "pending_approval", "pushed"):
            await self.push_fix(r)

    async def run_remediation(self, r: Running, auto_push: bool) -> bool:
        tid = r.task_id
        with session_scope() as db:
            t = self._owned(db, tid, S.IN_PROGRESS)
            resolved = self._route_or_review(db, t)
            if resolved is None:
                return False
            _, route = resolved
            snap = _snapshot(t)
            diag = db.scalar(select(Comment).where(Comment.task_id == tid, Comment.kind == "diagnosis")
                             .order_by(Comment.id.desc()).limit(1))
            if diag is None or not diag.data:
                transition(db, t, S.NEEDS_REVIEW, "no diagnosis available for remediation", level="error")
                return False
            diag_data = diag.data
            t.activity = "Preparing isolated worktree"
        repo, number, sha = snap["repo"], snap["pr_number"], snap["expected_sha"]

        pr = await asyncio.to_thread(self.gh.get_pr, repo, number)
        if pr.head_sha != sha:
            with session_scope() as db:
                t = self._owned(db, tid, S.IN_PROGRESS)
                t.head_sha = pr.head_sha
                retarget_to_head(db, t, f"PR head is {pr.head_sha[:7]}, expected {sha[:7]}")
            return False

        await self.deps.worktrees.fetch_pr(repo, number, snap["head_branch"], snap["base_branch"])
        worktree = await self.deps.worktrees.create(repo, tid, f"fix-a{snap['attempt']}", sha)
        bundle = Path(diag_data.get("bundle_dir") or worktree)
        diagnosis = {"classification": diag_data["reconciled"]["classification"],
                     "deterministic_findings": diag_data.get("findings", []),
                     **{k: diag_data["analysis"][k] for k in ("root_cause", "affected_files", "proposed_fix")}}

        run_id = self._start_run(tid, "remediation", snap["attempt"])
        emit = self._emitter(run_id, tid)
        self.set_activity(tid, f"Remediation Subagent {route.remediation_agent} is applying the fix "
                               f"(attempt {snap['attempt']}/{snap['max_attempts']})")
        tools, allowed = remediation_contract.tool_permissions(worktree, route)
        spec = AgentSpec(
            prompt=remediation_contract.build_prompt(diagnosis, worktree, bundle, route),
            tools=tools,
            allowed_tools=allowed,
            json_schema=remediation_contract.output_json_schema(),
            add_dirs=[worktree, bundle],
            agent=route.remediation_agent,
            timeout=self.settings.remediation_timeout_seconds,
        )
        res = await self.deps.run_agent(spec, emit, r.cancel, self._set_pid(run_id))
        output, error = None, None
        if res.status == "succeeded":
            try:
                output = remediation_contract.RemediationOutput.model_validate(res.structured)
            except ValidationError as exc:
                error = f"remediation output failed schema validation: {exc}"
        self._finish_run(run_id, res, status="failed" if error else None, error=error)
        if res.status == "cancelled":
            await self.deps.worktrees.remove(repo, worktree)
            raise StageAborted("remediation cancelled")

        # Deterministic post-checks, independent of what the agent claims.
        self.set_activity(tid, "Verifying scope and running local validation")
        diff, files = await self.deps.worktrees.working_changes(worktree)
        scope = remediation_contract.check_scope(files, route)
        report = await self.deps.validate(worktree, route)
        valid = bool(report.get("valid"))
        emit("system", f"scope check: {'ok' if scope.ok else '; '.join(scope.violations)} · "
                       f"local validation: {'valid' if valid else 'INVALID'}")

        problems = []
        if output is None:
            problems.append(f"agent did not produce a valid result: {error or res.error or res.status}")
        elif output.status == "blocked":
            problems.append(f"agent blocked: {output.blocked_reason or output.summary}")
        if not scope.ok:
            problems.append("scope violation: " + "; ".join(scope.violations))
        if not valid:
            problems.append(f"local validation failed: {len(local_validation.findings_of(report))} finding(s)")

        commit_sha = None
        if not problems:
            message = (f"fix: {output.summary[:68].rstrip('.')}\n\n"
                       f"{output.rationale.strip()}\n\nClassification: {diagnosis['classification']}\n"
                       f"Route: {route.check} → {route.remediation_agent}\n"
                       f"Remediation-Task: {tid} (attempt {snap['attempt']})\nGenerated-By: AI Remediation Control Plane")
            commit_sha = await self.deps.worktrees.commit(worktree, message)
        else:
            await self.deps.worktrees.remove(repo, worktree)

        with session_scope() as db:
            t = self._owned(db, tid, S.IN_PROGRESS)
            rem = Remediation(
                task_id=tid, attempt=snap["attempt"], run_id=run_id, base_sha=sha,
                summary=(output.summary if output else (error or res.error or "")) or "",
                diff=redact(diff), files=[f.__dict__ for f in files], scope_ok=scope.ok,
                scope_violations=scope.violations, validation=report, validation_passed=valid,
                commit_sha=commit_sha, push_status="pending_approval" if commit_sha else "rejected",
                worktree_path=str(worktree) if commit_sha else None,
            )
            db.add(rem)
            db.add(ValidationRun(task_id=tid, sha=commit_sha or sha, purpose="post-remediation", valid=valid,
                                 exit_code=report.get("exit_code", -1), report=report))
            body = [f"### Remediation attempt {snap['attempt']} — {'ready' if commit_sha else 'rejected'}", ""]
            if output:
                body += [output.summary, "", f"**Rationale:** {output.rationale}", ""]
                body += [f"- `{c.file}` — {c.description}" for c in output.changes]
                body += ["", f"**Agent-reported validation:** {output.validation.summary}"]
            body += ["", f"**Scope check:** {'passed' if scope.ok else '; '.join(scope.violations)} "
                         f"({scope.changed_lines} changed lines)",
                     f"**Local validation (control plane):** {'passed' if valid else 'failed'}"]
            if commit_sha:
                body.append(f"**Commit:** `{commit_sha[:12]}` (not pushed yet)")
            if problems:
                body += ["", "**Rejected because:** " + "; ".join(problems)]
            if diff:
                body += ["", "```diff", redact(diff)[:6000], "```"]
            add_comment(db, tid, "remediation-agent", "remediation", "\n".join(body),
                        data={"run_id": run_id, "commit_sha": commit_sha, "problems": problems})
            if problems:
                transition(db, t, S.NEEDS_REVIEW, "; ".join(problems)[:500], level="error")
                t.resolution = "remediation_rejected"
                self._queue_notification(db, t, "needs_review", "; ".join(problems))
                return False
            record_event(db, tid, "fix_committed", f"Fix committed locally as {commit_sha[:7]} "
                                                    f"({len(files)} file(s), {scope.changed_lines} lines)",
                         level="success", data={"commit_sha": commit_sha})
            if not auto_push or t.paused:
                t.pending_action = PendingAction.PUSH
                t.activity = "Fix validated locally — waiting for “Approve Push”"
                record_event(db, tid, "awaiting_approval", "Auto Push is off — waiting for “Approve Push”",
                             level="warning")
                return False
        await self.push_fix(r)
        return True

    async def push_fix(self, r: Running) -> None:
        tid = r.task_id
        with session_scope() as db:
            t = self._owned(db, tid, S.IN_PROGRESS)
            resolved = self._route_or_review(db, t)
            if resolved is None:
                return
            repo_cfg, _ = resolved
            rem = latest_remediation(db, tid, t.attempt)
            if rem is None or not rem.commit_sha:
                raise StageAborted("nothing to push")
            snap, commit_sha, wt = _snapshot(t), rem.commit_sha, rem.worktree_path
            t.activity = f"Pushing {commit_sha[:7]} to {t.head_branch}"
        repo, branch = snap["repo"], snap["head_branch"]

        if repo_cfg.is_protected(branch):
            self._reject_push(tid, f"branch {branch!r} is protected — the control plane never pushes there")
            return
        pr = await asyncio.to_thread(self.gh.get_pr, repo, snap["pr_number"])
        if pr.state != "open":
            self._reject_push(tid, f"PR is {pr.state}")
            return
        if pr.head_sha == commit_sha:
            already = True  # recovered after a crash between push and bookkeeping
        elif pr.head_sha != snap["expected_sha"]:
            with session_scope() as db:
                t = self._owned(db, tid, S.IN_PROGRESS)
                rem = latest_remediation(db, tid, t.attempt)
                rem.push_status, rem.push_error = "discarded", f"PR head moved to {pr.head_sha[:7]}"
                t.head_sha = pr.head_sha
                retarget_to_head(db, t, f"PR head moved to {pr.head_sha[:7]} before push — fix discarded")
            return
        else:
            already = False
            if not wt or not Path(wt).exists():
                with session_scope() as db:
                    t = self._owned(db, tid, S.IN_PROGRESS)
                    rem = latest_remediation(db, tid, t.attempt)
                    rem.push_status, rem.push_error = "discarded", "worktree lost (restart) — regenerating fix"
                    db.flush()
                    db.delete(rem)
                    record_event(db, tid, "fix_regenerate", "Local fix commit was lost; remediation will run again",
                                 level="warning")
                return
            try:
                await self.deps.worktrees.push(Path(wt), branch, repo_cfg.protected_branches)
            except GitError as exc:
                self._reject_push(tid, f"git push failed: {exc}")
                return

        with session_scope() as db:
            t = self._owned(db, tid, S.IN_PROGRESS)
            rem = latest_remediation(db, tid, t.attempt)
            rem.push_status, rem.pushed_at = "pushed", utcnow()
            t.expected_sha = t.head_sha = commit_sha
            t.ci_status, t.ci_waiting_since, t.ci_next_check_at = None, utcnow(), utcnow() + timedelta(seconds=self.settings.ci_poll_interval_seconds)
            record_event(db, tid, "pushed", f"Pushed {commit_sha[:7]} to {branch}" + (" (already on remote)" if already else ""),
                         level="success", data={"commit_sha": commit_sha, "branch": branch})
            transition(db, t, S.VALIDATING, f"waiting for GitHub Actions on {commit_sha[:7]}")
        if wt:
            await self.deps.worktrees.remove(repo, Path(wt))

    def _reject_push(self, tid: int, reason: str) -> None:
        with session_scope() as db:
            t = self._owned(db, tid, S.IN_PROGRESS)
            rem = latest_remediation(db, tid, t.attempt)
            if rem:
                rem.push_status, rem.push_error = "failed", reason
            transition(db, t, S.NEEDS_REVIEW, reason, level="error")
            t.resolution = "push_failed"
            self._queue_notification(db, t, "needs_review", reason)

    # ------------------------------------------------------------------ notifications
    def _queue_notification(self, db, t: Task, kind: str, reason: str | None) -> None:
        db.add(Notification(task_id=t.id, kind=kind, status="queued", preview=redact(reason or "")[:1000]))

    async def flush_notifications(self) -> None:
        with session_scope() as db:
            queued = db.scalars(select(Notification).where(Notification.status == "queued")).all()
            payloads = []
            for n in queued:
                t = db.get(Task, n.task_id)
                payloads.append((n.id, slack.build_message(n.kind, _task_dict(t), self._details(db, t, n))))
        for nid, payload in payloads:
            status, error = await self.deps.slack_send(payload)
            with session_scope() as db:
                n = db.get(Notification, nid)
                n.status, n.error = status, error
                n.preview = payload.get("text")
                record_event(db, n.task_id, "notification",
                             f"Slack {n.kind} notification {status}" + (f": {error}" if error else ""),
                             level={"sent": "success", "failed": "error"}.get(status, "info"))

    def _details(self, db, t: Task, n: Notification) -> dict:
        diag = db.scalar(select(Comment).where(Comment.task_id == t.id, Comment.kind == "diagnosis")
                         .order_by(Comment.id.desc()).limit(1))
        rem = db.scalar(select(Remediation).where(Remediation.task_id == t.id).order_by(Remediation.id.desc()).limit(1))
        findings = (diag.data or {}).get("findings", []) if diag else []
        problem = "; ".join(f"{f.get('category')}: {f.get('message')}"[:250] for f in findings[:3])
        details = {"problem": problem or None, "reason": n.preview if n.kind != "remediated" else None}
        if rem:
            details["files"] = [f["path"] for f in rem.files or []]
            details["diff"] = rem.diff
            if rem.commit_sha and rem.push_status == "pushed":
                details["commit_url"] = f"https://github.com/{t.repo}/commit/{rem.commit_sha}"
        if n.kind == "remediated":
            details["validation"] = (f"Local validator ✅ · GitHub Actions ✅ "
                                     f"({t.route or 'required checks'}) on `{t.expected_sha[:7]}`")
        else:
            details["validation"] = f"CI: {t.ci_status or 'unknown'}"
        return details


# ---------------------------------------------------------------------- helpers
def latest_remediation(db, task_id: int, attempt: int) -> Remediation | None:
    return db.scalar(
        select(Remediation)
        .where(and_(Remediation.task_id == task_id, Remediation.attempt == attempt,
                    Remediation.push_status != "discarded"))
        .order_by(Remediation.id.desc()).limit(1)
    )


def start_remediation(db, t: Task, reason: str) -> None:
    """TODO → IN_PROGRESS, consuming one remediation attempt."""
    if t.attempt >= t.max_attempts:
        transition(db, t, S.NEEDS_REVIEW, f"remediation attempts exhausted ({t.attempt}/{t.max_attempts})",
                   level="warning")
        t.resolution = "attempts_exhausted"
        return
    t.attempt += 1
    transition(db, t, S.IN_PROGRESS, f"{reason} — attempt {t.attempt}/{t.max_attempts}")


def _snapshot(t: Task) -> dict:
    return {k: getattr(t, k) for k in ("id", "repo", "pr_number", "pr_url", "title", "author", "head_branch",
                                        "base_branch", "head_sha", "expected_sha", "attempt", "max_attempts",
                                        "route")}


def _task_dict(t: Task) -> dict:
    return {"id": t.id, "repo": t.repo, "pr_number": t.pr_number, "pr_url": t.pr_url, "title": t.title,
            "classification": t.classification, "root_cause": t.root_cause}


async def main() -> None:
    """Standalone worker: `python -m app.worker` (set RUN_WORKER=false on the API process)."""
    import signal

    from app.db import init_engine, run_migrations

    logging.basicConfig(level=get_settings().log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    run_migrations()
    init_engine()
    worker = Worker()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, worker.stop)
    await worker.run_forever()
