"""Advance the workshop Slack dialogue using durable agent operations."""

from datetime import timedelta
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from app.agents.workshop import (
    BlockerNotice,
    DescriptionBlock,
    NeedsIntervention,
    Proposal,
    Questions,
    Reply,
    StageInput,
)
from app.db import session_scope, utcnow
from app.integrations.training_jira import TrainingJira
from app.models.jira_workflow import JiraWorkflowDecision, JiraWorkflowDraft, JiraWorkflowEvent, JiraWorkflowOperation
from app.models.jira_workflow import JiraWorkflowRun as Run
from app.models.jira_workflow import JiraWorkflowState as State
from app.orchestration.workshop_blockers import post_blocker_fallback, queue_blocker, record_blocker
from app.orchestration.workshop_runner import WorkshopAttempt
from app.services.workshop_replies import enqueue_reply

MAX_ATTEMPTS = 2
DIALOG_STATES = (
    State.DISCOVERED, State.WAITING_FOR_REPLY, State.WAITING_FOR_APPROVAL,
    State.WAITING_FOR_REVISION, State.NEEDS_INTERVENTION,
)


def _latest_draft(db: Session, run_id: str) -> JiraWorkflowDraft | None:
    return db.scalar(select(JiraWorkflowDraft).where(JiraWorkflowDraft.run_id == run_id)
                     .order_by(JiraWorkflowDraft.version.desc()).limit(1))


def _history(db: Session, run_id: str) -> tuple[list[Reply], Decimal]:
    entries = []
    latest_prompt = Decimal(0)
    for op in db.scalars(select(JiraWorkflowOperation).where(
        JiraWorkflowOperation.run_id == run_id, JiraWorkflowOperation.kind == "post_reply",
        JiraWorkflowOperation.status == "opened",
    )):
        ts = Decimal(op.result["thread_ts"])
        entries.append((ts, Reply(actor="agent", text=op.payload["text"])))
        latest_prompt = max(latest_prompt, ts)
    for event in db.scalars(select(JiraWorkflowEvent).where(
        JiraWorkflowEvent.run_id == run_id, JiraWorkflowEvent.event_type == "slack.thread_reply",
        JiraWorkflowEvent.outcome == "accepted",
    )):
        entries.append((Decimal(event.payload["message_ts"]), Reply(actor="reporter", text=event.payload["text"])))
    return [reply for _, reply in sorted(entries, key=lambda item: item[0])], latest_prompt


def _event_stage(db: Session, run: Run, draft: JiraWorkflowDraft | None, latest_prompt: Decimal):
    if run.state == State.WAITING_FOR_REVISION and draft:
        revision = db.scalar(select(JiraWorkflowEvent).join(
            JiraWorkflowDecision, JiraWorkflowDecision.source_event_id == JiraWorkflowEvent.event_id,
        ).where(JiraWorkflowDecision.draft_id == draft.draft_id,
                JiraWorkflowDecision.decision == "request_revision"))
        if revision:
            latest_prompt = Decimal(revision.payload["action_ts"])
    events = db.scalars(select(JiraWorkflowEvent).where(
        JiraWorkflowEvent.run_id == run.run_id, JiraWorkflowEvent.processed_at.is_(None),
        JiraWorkflowEvent.event_type.in_(("slack.thread_reply", "slack.draft_action")),
    ).order_by(JiraWorkflowEvent.id))
    for event in events:
        payload = event.payload
        action = payload.get("action")
        if action == "approve":
            # Approval is handled separately. An earlier valid click wins over later revisions.
            if run.state == State.WAITING_FOR_APPROVAL and _matches_draft(run, draft, event):
                return None, None
            continue
        event.processed_at = utcnow()
        if payload.get("actor_slack_user_id") != run.slack_user_id:
            event.outcome = "actor_mismatch"
        elif event.event_type == "slack.draft_action":
            if action != "request_revision" or run.state != State.WAITING_FOR_APPROVAL or not _matches_draft(run, draft, event):
                event.outcome = "stale_draft"
                continue
            assert draft is not None
            db.add(JiraWorkflowDecision(
                decision_id=f"revision-{event.id}", run_id=run.run_id, draft_id=draft.draft_id,
                actor_slack_user_id=run.slack_user_id, decision="request_revision", source_event_id=event.event_id,
            ))
            draft.status = "revision_requested"
            run.state = State.WAITING_FOR_REVISION
            event.outcome = "accepted"
            return "request_revision", event
        elif run.state in (State.WAITING_FOR_REPLY, State.WAITING_FOR_REVISION, State.NEEDS_INTERVENTION):
            try:
                newer = Decimal(payload["message_ts"]) > latest_prompt
            except (InvalidOperation, KeyError, TypeError):
                newer = False
            if newer and isinstance(payload.get("text"), str) and payload["text"].strip():
                event.outcome = "accepted"
                return {
                    State.WAITING_FOR_REPLY: "reply",
                    State.WAITING_FOR_REVISION: "revision",
                    State.NEEDS_INTERVENTION: "recovery",
                }[run.state], event
            event.outcome = "stale_reply"
        else:
            event.outcome = "unexpected_state"
    return None, None


def _matches_draft(run: Run, draft: JiraWorkflowDraft | None, event: JiraWorkflowEvent) -> bool:
    p = event.payload
    return bool(draft and draft.status == "pending_approval" and draft.slack_message_ts
                and p.get("actor_slack_user_id") == run.slack_user_id
                and (p.get("draft_id"), p.get("draft_version"), p.get("message_ts"))
                == (draft.draft_id, draft.version, draft.slack_message_ts))


def claim_step(timeout: float) -> tuple[str, str, int, StageInput] | None:
    with session_scope() as db:
        # Serialize selection and claim, without holding the lock during Claude execution.
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
        cutoff = utcnow() - timedelta(seconds=timeout + 30)
        op = db.scalar(select(JiraWorkflowOperation).where(
            JiraWorkflowOperation.kind == "agent_stage",
            or_(JiraWorkflowOperation.status == "pending",
                (JiraWorkflowOperation.status == "running") & (JiraWorkflowOperation.updated_at < cutoff)),
        ).order_by(JiraWorkflowOperation.updated_at).limit(1))
        if op:
            if op.attempts >= MAX_ATTEMPTS:
                run = db.get(Run, op.run_id)
                _stop_stage(db, run, op, "agent execution interrupted before completion")
                return None
            op.status = "running"
            op.attempts += 1
            return op.operation_id, op.run_id, op.attempts, StageInput.model_validate(op.payload)

        active_work = exists().where(
            JiraWorkflowOperation.run_id == Run.run_id,
            JiraWorkflowOperation.kind.in_(("agent_stage", "post_reply")),
            JiraWorkflowOperation.status.in_(("pending", "running")),
        )
        for run in db.scalars(select(Run).where(
            Run.source_kind == "training", Run.slack_thread_ts.is_not(None), Run.state.in_(DIALOG_STATES), ~active_work,
        ).order_by(Run.created_at)):
            draft = _latest_draft(db, run.run_id)
            history, latest_prompt = _history(db, run.run_id)
            if run.state == State.DISCOVERED:
                if draft:  # Preserve manually published pre-dialogue workshop drafts.
                    continue
                stage, event = "triage", None
            else:
                stage, event = _event_stage(db, run, draft, latest_prompt)
                if stage is None:
                    continue
                history, _ = _history(db, run.run_id)
            issue = TrainingJira(db).get_issue(run.issue_id, run.source_reporter_id)
            if issue is None:
                queue_blocker(db, run, f"issue-{event.id if event else 'triage'}", "jira",
                              "training issue unavailable", BlockerNotice(
                                  reason="Навчальна задача зараз недоступна.",
                                  next_step="Перевір, чи задача доступна, і напиши в треді, коли можна продовжити.",
                              ))
                continue
            blocker = None
            if stage == "recovery":
                failure = db.scalar(select(JiraWorkflowEvent).where(
                    JiraWorkflowEvent.run_id == run.run_id, JiraWorkflowEvent.event_type == "workshop.blocker",
                ).order_by(JiraWorkflowEvent.id.desc()).limit(1))
                if failure and failure.payload.get("notice") and failure.payload.get("error") == run.last_error:
                    blocker = BlockerNotice.model_validate(failure.payload["notice"])
            request = StageInput(
                stage=stage, issue=issue, replies=history, follow_up_rounds_used=run.follow_up_rounds_used,
                previous_block=DescriptionBlock.model_validate(draft.block)
                if draft and stage in ("revision", "recovery") else None,
                blocker=blocker,
            )
            key = f"event-{event.id}" if event else "triage"
            op_id = f"{run.run_id}:agent:{key}"
            db.add(JiraWorkflowOperation(
                operation_id=op_id, run_id=run.run_id, kind="agent_stage",
                status="running", attempts=1, payload=request.model_dump(mode="json"),
            ))
            if stage == "triage":
                run.state = State.TRIAGING
            elif stage == "recovery":
                run.state = State.WAITING_FOR_REVISION
            return op_id, run.run_id, 1, request
    return None


def _stop_stage(db: Session, run: Run, op: JiraWorkflowOperation, reason: str) -> None:
    op.status = "failed"
    stage = op.payload["stage"]
    key = op.operation_id.rsplit(":", 1)[-1]
    if stage == "blocker":
        post_blocker_fallback(db, run, key, BlockerNotice.model_validate(op.payload["blocker"]))
    elif stage == "result" and run.state == State.APPLIED:
        issue_key = op.payload["issue"]["issue_key"]
        enqueue_reply(db, run.run_id, key,
                      text=f"Опис задачі {issue_key} доповнено погодженим блоком. Статус лишився New.")
    else:
        queue_blocker(db, run, key, stage, reason, BlockerNotice(
            reason="Не вдалося продовжити цей етап обробки задачі.",
            next_step="Напиши в треді, щоб продовжити, або уточни, що потрібно змінити.",
        ))


def _render(block: DescriptionBlock) -> str:
    lines = [block.heading, "", "Сценарій:"]
    lines += [f"{number}. {step}" for number, step in enumerate(block.steps, 1)]
    lines += ["", f"Поточний стан: {block.actual}", f"Очікуваний результат: {block.expected}"]
    if block.evidence:
        lines += ["", "Докази:", *[f"- {item.path}#{item.symbol}" for item in block.evidence]]
    if block.open_questions:
        lines += ["", "Відкриті питання:", *[f"- {question}" for question in block.open_questions]]
    return "\n".join(lines)


def finish_step(op_id: str, claim_attempt: int, result: WorkshopAttempt) -> None:
    with session_scope() as db:
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
        op = db.get(JiraWorkflowOperation, op_id)
        if op is None or op.status != "running" or op.attempts != claim_attempt:
            return
        run = db.get(Run, op.run_id)
        assert run is not None
        op.result = {"attempt_id": result.attempt_id, "status": result.status, "error": result.error}
        if op.payload["stage"] == "blocker" and run.state != State.NEEDS_INTERVENTION:
            op.status = "superseded"
            return
        if result.status == "cancelled":
            op.status, op.attempts = "pending", max(0, op.attempts - 1)
            return
        if result.output is None:
            if op.attempts < MAX_ATTEMPTS:
                op.status = "pending"
            else:
                _stop_stage(db, run, op, result.error or "agent stage failed")
            return

        output = result.output
        key = op.operation_id.rsplit(":", 1)[-1]
        if isinstance(output, Proposal):
            rendered = _render(output.block)
            if len(rendered) > 12000:
                _stop_stage(db, run, op, "draft exceeds Slack length limit")
                return
            previous = _latest_draft(db, run.run_id)
            draft = JiraWorkflowDraft(
                draft_id=f"draft-{uuid4().hex}", run_id=run.run_id, version=(previous.version if previous else 0) + 1,
                based_on_description_revision=op.payload["issue"]["description_revision"],
                rendered_append=rendered, block=output.block.model_dump(mode="json"),
            )
            db.add(draft)
            db.flush()
            enqueue_reply(db, run.run_id, key, output.slack_text, draft_id=draft.draft_id)
            run.state = State.WAITING_FOR_APPROVAL
        else:
            enqueue_reply(db, run.run_id, key, output.slack_text)
            if isinstance(output, Questions):
                if op.payload["stage"] == "reply":
                    run.follow_up_rounds_used += 1
                run.state = State.WAITING_FOR_REPLY
            elif isinstance(output, NeedsIntervention):
                record_blocker(db, run, f"blocker-{key}", op.payload["stage"], output.reason)
        op.status = "succeeded"
