"""Scheduler / worker behaviour with fake GitHub, git, agents and Slack."""

from __future__ import annotations

import asyncio
from datetime import timedelta

from sqlalchemy import select

from app.db import session_scope, utcnow
from app.models import AgentRun, Notification, Remediation, Task, TaskState
from app.orchestration.worker import Worker
from app.services import actions
from app.services.registration import register_pr
from app.services.settings_store import update_automation
from tests.conftest import SHA1, SHA_FIX, pr_info


def make_task(auto_push: bool = True, auto_analyze: bool = True, auto_remediate: bool = True) -> int:
    with session_scope() as db:
        update_automation(db, auto_analyze=auto_analyze, auto_remediate=auto_remediate, auto_push=auto_push)
        return register_pr(db, pr_info(), "hook").task.id


def task(tid: int) -> Task:
    with session_scope() as db:
        return db.get(Task, tid)


async def test_full_autonomous_remediation(harness):
    tid = make_task(auto_push=True)
    harness.github.set_check(SHA1, "in_progress", None)
    await harness.drain(1)
    assert task(tid).state == TaskState.WAITING_CI

    harness.github.checks[SHA1] = []
    harness.github.set_check(SHA1, "completed", "failure")
    await harness.drain(4)
    t = task(tid)
    assert t.state == TaskState.VALIDATING, t.state
    assert t.classification == "LOGICAL_CONFIGURATION_ERROR"
    assert t.expected_sha == SHA_FIX and t.attempt == 1
    assert harness.agents.calls == ["analysis", "remediation"]
    assert harness.worktrees.pushes and harness.worktrees.pushes[0][1] == "demo/x"

    harness.github.set_check(SHA_FIX, "completed", "success")
    await harness.drain(2)
    t = task(tid)
    assert t.state == TaskState.DONE and t.resolution == "remediated"
    assert len(harness.slack) == 1 and "succeeded" in harness.slack[0]["text"]
    with session_scope() as db:
        n = db.scalar(select(Notification).where(Notification.task_id == tid))
        assert n.status == "sent" and n.kind == "remediated"
        rem = db.scalar(select(Remediation).where(Remediation.task_id == tid))
        assert rem.push_status == "pushed" and rem.validation_passed and rem.scope_ok


async def test_green_pr_needs_no_agent(harness):
    tid = make_task()
    harness.github.set_check(SHA1, "completed", "success")
    await harness.drain(2)
    t = task(tid)
    assert t.state == TaskState.DONE and t.resolution == "passed_without_remediation"
    assert harness.agents.calls == [] and harness.slack == []


async def test_push_requires_approval_when_auto_push_off(harness):
    tid = make_task(auto_push=False)
    harness.github.set_check(SHA1, "completed", "failure")
    await harness.drain(5)
    t = task(tid)
    assert t.state == TaskState.IN_PROGRESS and t.pending_action == "push"
    assert harness.worktrees.pushes == []

    with session_scope() as db:
        t = db.get(Task, tid)
        assert "approve_push" in actions.available_actions(db, t)
        actions.perform(db, t, actions.Action.APPROVE_PUSH)
    await harness.drain(2)
    assert task(tid).state == TaskState.VALIDATING
    assert len(harness.worktrees.pushes) == 1


async def test_manual_analyze_and_remediate(harness):
    tid = make_task(auto_analyze=False, auto_remediate=False)
    harness.github.set_check(SHA1, "completed", "failure")
    await harness.drain(3)
    t = task(tid)
    assert t.state == TaskState.WAITING_CI and t.pending_action == "analyze"
    assert harness.agents.calls == []

    with session_scope() as db:
        actions.perform(db, db.get(Task, tid), actions.Action.ANALYZE)
    await harness.drain(3)
    t = task(tid)
    assert t.state == TaskState.TODO and t.pending_action == "remediate"

    with session_scope() as db:
        actions.perform(db, db.get(Task, tid), actions.Action.START_REMEDIATION)
    await harness.drain(3)
    assert task(tid).state == TaskState.VALIDATING


async def test_retry_limit_moves_to_needs_review(harness):
    tid = make_task()
    harness.github.set_check(SHA1, "completed", "failure")
    await harness.drain(4)
    assert task(tid).state == TaskState.VALIDATING

    harness.github.set_check(SHA_FIX, "completed", "failure")  # first fix fails CI
    harness.worktrees.commit_sha = "e" * 40
    await harness.drain(5)
    t = task(tid)
    assert t.attempt == 2 and t.state == TaskState.VALIDATING and t.expected_sha == "e" * 40

    harness.github.set_check("e" * 40, "completed", "failure")  # second fix fails too
    await harness.drain(3)
    t = task(tid)
    assert t.state == TaskState.NEEDS_REVIEW and t.resolution == "attempts_exhausted"
    assert harness.agents.calls.count("remediation") == 2


async def test_non_remediable_diagnosis_needs_review(harness):
    harness.agents.analysis = {**harness.agents.analysis, "auto_remediation_appropriate": False,
                               "auto_remediation_rationale": "needs a product decision"}
    tid = make_task()
    harness.github.set_check(SHA1, "completed", "failure")
    await harness.drain(3)
    t = task(tid)
    assert t.state == TaskState.NEEDS_REVIEW and harness.agents.calls == ["analysis"]
    assert harness.slack and "review" in harness.slack[0]["text"]


async def test_out_of_scope_diff_is_rejected(harness):
    from app.integrations.git_worktree import ChangedFile

    harness.worktrees.changed = [ChangedFile(".github/workflows/helm-validate.yaml", "M", 3, 3)]
    tid = make_task()
    harness.github.set_check(SHA1, "completed", "failure")
    await harness.drain(4)
    t = task(tid)
    assert t.state == TaskState.NEEDS_REVIEW and t.resolution == "remediation_rejected"
    assert harness.worktrees.pushes == []


async def test_failed_local_validation_blocks_push(harness):
    tid = make_task()
    harness.validate_results.extend([
        {"valid": False, "charts": [], "exit_code": 1},  # pre-analysis
        {"valid": False, "charts": [{"findings": [{"category": "SYNTAX_ERROR"}]}], "exit_code": 1},  # post-fix
    ])
    harness.github.set_check(SHA1, "completed", "failure")
    await harness.drain(4)
    assert task(tid).state == TaskState.NEEDS_REVIEW
    assert harness.worktrees.pushes == []


async def test_cancel_kills_running_agent(harness):
    harness.agents.block = True
    tid = make_task()
    harness.github.set_check(SHA1, "completed", "failure")
    await harness.worker.tick()  # WAITING_CI -> ANALYZING
    await harness.worker.tick()  # dispatch analysis (blocks)
    assert tid in harness.worker.running
    await asyncio.sleep(0.05)
    with session_scope() as db:
        actions.perform(db, db.get(Task, tid), actions.Action.CANCEL)
    await harness.worker.tick()  # watcher signals cancel
    await asyncio.wait_for(asyncio.gather(*[r.job for r in harness.worker.running.values()]), 5)
    t = task(tid)
    assert t.state == TaskState.FAILED and t.resolution == "cancelled" and t.lease_owner is None
    with session_scope() as db:
        run = db.scalar(select(AgentRun).where(AgentRun.task_id == tid))
        assert run.status == "cancelled"


async def test_pause_prevents_next_stage(harness):
    tid = make_task()
    with session_scope() as db:
        actions.perform(db, db.get(Task, tid), actions.Action.PAUSE)
    harness.github.set_check(SHA1, "completed", "failure")
    await harness.drain(3)
    assert task(tid).state == TaskState.WAITING_CI and harness.agents.calls == []
    with session_scope() as db:
        actions.perform(db, db.get(Task, tid), actions.Action.RESUME)
    await harness.drain(4)
    assert task(tid).state == TaskState.VALIDATING


async def test_atomic_claim_single_winner(harness):
    tid = make_task()
    with session_scope() as db:
        t = db.get(Task, tid)
        t.state = TaskState.ANALYZING
    other = Worker(harness.worker.deps, worker_id="other")
    assert harness.worker.claim(tid, TaskState.ANALYZING) is True
    assert other.claim(tid, TaskState.ANALYZING) is False
    assert harness.worker.claim(tid, TaskState.TODO) is False  # wrong state never claims


async def test_recovery_after_interrupted_worker(harness):
    tid = make_task()
    with session_scope() as db:
        t = db.get(Task, tid)
        t.state = TaskState.ANALYZING
        t.lease_owner = "dead-worker"
        t.lease_expires_at = utcnow() - timedelta(seconds=5)
        db.add(AgentRun(task_id=tid, kind="analysis", status="running", worker_id="dead-worker"))
    harness.github.set_check(SHA1, "completed", "failure")
    harness.worker.recover()
    t = task(tid)
    assert t.lease_owner is None
    with session_scope() as db:
        assert db.scalar(select(AgentRun).where(AgentRun.task_id == tid)).status == "interrupted"
    await harness.drain(4)
    assert task(tid).state == TaskState.VALIDATING


async def test_new_developer_commit_during_validation_retargets(harness):
    tid = make_task()
    harness.github.set_check(SHA1, "completed", "failure")
    await harness.drain(4)
    assert task(tid).state == TaskState.VALIDATING
    with session_scope() as db:
        res = register_pr(db, pr_info(sha="b" * 40), "webhook")
        assert res.retargeted
    t = task(tid)
    assert t.state == TaskState.WAITING_CI and t.expected_sha == "b" * 40 and t.attempt == 0


async def test_ci_cancelled_needs_review(harness):
    tid = make_task()
    harness.github.set_check(SHA1, "completed", "cancelled")
    await harness.drain(2)
    assert task(tid).state == TaskState.NEEDS_REVIEW


async def test_analysis_crash_retries_then_fails(harness):
    async def broken(spec, emit, cancel, on_start=None):
        from app.integrations.claude_runner import AgentResult
        harness.agents.calls.append("analysis")
        return AgentResult(status="failed", error="boom")

    harness.worker.deps.run_agent = broken
    tid = make_task()
    harness.github.set_check(SHA1, "completed", "failure")
    await harness.drain(5)
    t = task(tid)
    assert t.state == TaskState.FAILED and t.resolution == "analysis_failed"
    assert harness.agents.calls == ["analysis", "analysis"]


async def test_graceful_shutdown_releases_leases(harness):
    harness.agents.block = True
    tid = make_task()
    harness.github.set_check(SHA1, "completed", "failure")
    await harness.worker.tick()
    await harness.worker.tick()
    assert tid in harness.worker.running
    await harness.worker.shutdown()
    t = task(tid)
    assert t.lease_owner is None and t.state == TaskState.ANALYZING
    with session_scope() as db:
        assert db.scalar(select(AgentRun).where(AgentRun.task_id == tid)).status in ("interrupted", "cancelled")
