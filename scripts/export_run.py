#!/usr/bin/env python3
"""Export every artifact of one finished task into a folder, laid out by pipeline stage.

  backend/.venv/bin/python scripts/export_run.py 14 docs/examples/pr-16-scenario-c

Reads the control plane's database and run bundles (read-only) and the task detail API, rebuilds the exact
Slack payload, and replaces the local checkout path with `<control-plane>` so the output can be committed.
Used to produce docs/examples/.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / ".claude/hooks")]

import register_pr  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import get_engine, init_engine, session_scope  # noqa: E402
from app.integrations import slack  # noqa: E402
from app.models import Notification, Task  # noqa: E402
from app.orchestration.worker import Worker, _task_dict  # noqa: E402


def parse(value):
    if isinstance(value, str) and value[:1] in "{[":
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


class Exporter:
    def __init__(self, task_id: int, out: Path, api: str):
        self.task_id, self.out, self.api = task_id, out, api
        self.conn = get_engine().connect()

    def rows(self, sql: str, **params) -> list[dict]:
        return [dict(r._mapping) for r in self.conn.execute(text(sql), {"task": self.task_id, **params})]

    def write(self, rel: str, content) -> None:
        path = self.out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if not isinstance(content, str):
            content = json.dumps(content, indent=2, ensure_ascii=False, default=str)
        path.write_text(content if content.endswith("\n") else content + "\n")

    def registration(self) -> None:
        task = self.rows("select pr_url from tasks where id=:task")[0]
        payload = register_pr.resolve_pr("gh pr create", task["pr_url"], str(ROOT))
        # The PR head has since moved to the fix commit; show the payload as the hook sent it.
        payload["head_sha"] = self.rows("select sha from ci_snapshots where task_id=:task order by id limit 1")[0]["sha"]
        self.write("01-registration/hook-request.json", payload)

    def ci(self) -> None:
        snaps = self.rows("select sha, overall, checks, ts from ci_snapshots where task_id=:task order by id")
        self.write("02-ci/ci-snapshots.json", [{**s, "checks": parse(s["checks"])} for s in snaps])

    def agent_run(self, run: dict, folder: str) -> None:
        keys = ("id", "kind", "attempt", "status", "model", "num_turns", "cost_usd", "exit_code",
                "started_at", "finished_at")
        self.write(f"{folder}/agent-run.json", {k: run[k] for k in keys})
        self.write(f"{folder}/agent-output.json", parse(run["output"]))
        lines = self.rows("select ts, kind, text, detail from agent_log_lines where run_id=:run order by id",
                          run=run["id"])
        self.write(f"{folder}/agent-transcript.jsonl",
                   "\n".join(json.dumps({**ln, "detail": parse(ln["detail"])}, ensure_ascii=False, default=str)
                             for ln in lines))

    def agents(self) -> None:
        runs = self.rows("select * from agent_runs where task_id=:task order by id")
        analysis = next(r for r in runs if r["kind"] == "analysis")
        remediation = next(r for r in runs if r["kind"] == "remediation")
        bundle = get_settings().data_dir / f"runs/task-{self.task_id}/analysis-{analysis['id']}"
        for f in sorted(bundle.iterdir()):
            self.write(f"03-analysis/bundle/{f.name}", f.read_text())
        self.agent_run(analysis, "03-analysis")
        self.agent_run(remediation, "04-remediation")

        for c in self.rows("select kind, body_md from comments where task_id=:task order by id"):
            folder = "03-analysis" if c["kind"] == "diagnosis" else "04-remediation"
            self.write(f"{folder}/{c['kind']}-comment.md", c["body_md"])
        for v in self.rows("select sha, purpose, valid, exit_code, report, ts from validation_runs "
                           "where task_id=:task order by id"):
            folder = "03-analysis" if v["purpose"] == "pre-analysis" else "04-remediation"
            self.write(f"{folder}/validation-{v['purpose']}.json", {**v, "report": parse(v["report"])})

        rem = self.rows("select * from remediations where task_id=:task order by id desc limit 1")[0]
        self.write("04-remediation/fix.diff", rem["diff"])
        keys = ("attempt", "base_sha", "summary", "files", "scope_ok", "scope_violations", "validation_passed",
                "commit_sha", "push_status", "pushed_at")
        self.write("04-remediation/remediation-record.json", {k: parse(rem[k]) for k in keys})

    def notifications(self) -> None:
        with session_scope() as db:
            task = db.get(Task, self.task_id)
            for n in db.query(Notification).filter(Notification.task_id == self.task_id):
                payload = slack.build_message(n.kind, _task_dict(task), Worker._details(None, db, task, n))
                self.write(f"05-notification/slack-{n.kind}.json", payload)
                self.write(f"05-notification/notification-{n.kind}.json",
                           {"channel": n.channel, "kind": n.kind, "status": n.status, "preview": n.preview,
                            "ts": n.ts})

    def api_views(self) -> None:
        with urllib.request.urlopen(f"{self.api}/api/tasks/{self.task_id}", timeout=10) as resp:
            detail = json.load(resp)
        self.write("06-api/task-detail.json", detail)
        self.write("06-api/events-timeline.json",
                   [{k: e[k] for k in ("ts", "type", "level", "message")} for e in detail["events"]])

    def anonymize(self) -> None:
        for path in self.out.rglob("*"):
            if path.is_file():
                path.write_text(path.read_text().replace(str(get_settings().data_dir.parent), "<control-plane>"))

    def run(self) -> None:
        if self.out.exists():
            shutil.rmtree(self.out)
        self.registration()
        self.ci()
        self.agents()
        self.notifications()
        self.api_views()
        self.anonymize()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("task_id", type=int)
    parser.add_argument("out", type=Path)
    parser.add_argument("--api", default=f"http://127.0.0.1:{get_settings().api_port}")
    args = parser.parse_args()
    init_engine()
    Exporter(args.task_id, args.out.resolve(), args.api).run()
    print(f"exported task {args.task_id} → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
