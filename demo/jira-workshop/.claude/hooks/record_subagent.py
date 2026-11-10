"""Write only lifecycle metadata for the workshop runner to import."""

import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path


def main() -> None:
    event = json.load(sys.stdin)
    kind = event["hook_event_name"]
    agent_id = event["agent_id"]
    if kind not in ("SubagentStart", "SubagentStop") or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", agent_id):
        raise ValueError("invalid subagent lifecycle event")
    record = {"kind": kind, "agent_id": agent_id, "agent_type": event["agent_type"],
              "at": datetime.now(UTC).isoformat()}
    with (Path(__file__).resolve().parent / "subagents.jsonl").open("a", encoding="utf-8") as journal:
        journal.write(json.dumps(record) + "\n")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError):
        sys.exit("Could not record workshop subagent lifecycle event")
