"""Run the booking exercise with the workshop agents and a temporary SQLite database."""

import argparse
import asyncio
import json
from tempfile import TemporaryDirectory

from app.agents.workshop import Proposal, Reply, StageInput
from app.config import REPO_ROOT
from app.db import init_engine, run_migrations, session_scope
from app.integrations.claude_runner import run_agent
from app.integrations.training_jira import TrainingJira
from app.models.jira_workflow import JiraWorkflowProfile, JiraWorkflowRun
from app.orchestration.workshop_runner import run_workshop_stage

RUN_ID = "local-exercise"


async def exercise(reply_kind: str) -> None:
    with session_scope() as db:
        issue = TrainingJira(db).create_booking_issue("local-exercise-reporter")
        profile = JiraWorkflowProfile(
            profile_id=RUN_ID, local_instance_id=RUN_ID, source_kind=issue.source.kind,
            source_instance_id=issue.source.instance_id, source_reporter_id=issue.reporter_id,
            slack_workspace_id="TLOCAL", slack_user_id="ULOCAL",
        )
        db.add(profile)
        db.flush()
        db.add(JiraWorkflowRun(
            run_id=RUN_ID, profile_id=profile.profile_id, source_kind=issue.source.kind,
            source_instance_id=issue.source.instance_id, issue_id=issue.issue_id, issue_key=issue.issue_key,
            source_reporter_id=issue.reporter_id, slack_user_id=profile.slack_user_id,
        ))

    fixture = json.loads((REPO_ROOT / "demo/booking/scenario.json").read_text(encoding="utf-8"))
    cancel = asyncio.Event()

    async def run(request: StageInput):
        attempt = await run_workshop_stage(RUN_ID, request, cancel, run_agent)
        if attempt.output is None:
            raise RuntimeError(attempt.error or attempt.status)
        return attempt.output

    triage = await run(StageInput(stage="triage", issue=issue))
    if isinstance(triage, Proposal):
        print(f"Чернетка\n{triage.slack_text}\n\n{triage.block.model_dump_json(indent=2)}")
        return
    print(f"Уточнення\n{triage.slack_text}\n", flush=True)
    reply = fixture["replies"][reply_kind]
    print(f"Репортер\n{reply}\n", flush=True)
    replies = [Reply(actor="agent", text=triage.slack_text), Reply(actor="reporter", text=reply)]
    output = await run(StageInput(stage="reply", issue=issue, replies=replies))
    if output.kind == "ask_questions":
        follow_up = fixture["replies"]["follow_up"]
        print(f"Додаткове уточнення\n{output.slack_text}\n\nРепортер\n{follow_up}\n", flush=True)
        replies.extend([Reply(actor="agent", text=output.slack_text), Reply(actor="reporter", text=follow_up)])
        output = await run(StageInput(stage="reply", issue=issue, replies=replies, follow_up_rounds_used=1))
    if not isinstance(output, Proposal):
        raise RuntimeError(output.slack_text)
    print(f"Чернетка\n{output.slack_text}\n\n{output.block.model_dump_json(indent=2)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reply", choices=("complete", "incomplete"), default="complete")
    args = parser.parse_args()
    with TemporaryDirectory(prefix="workshop-exercise-") as directory:
        url = f"sqlite:///{directory}/exercise.db"
        run_migrations(url)
        engine = init_engine(url)
        try:
            asyncio.run(exercise(args.reply))
        except RuntimeError as exc:
            parser.exit(1, f"Вправу зупинено. {exc}\n")
        finally:
            engine.dispose()


if __name__ == "__main__":
    main()
