import { AlertTriangle, CheckCircle2, Clock, Hand, PauseCircle, XCircle, type LucideIcon } from "lucide-react";
import { shortSha } from "@/lib/format";
import { resolutionLabel } from "@/lib/states";
import type { TaskCard } from "@/services/api";

export interface Callout {
  tone: "info" | "warn" | "ok" | "bad";
  Icon: LucideIcon;
  title: string;
  body?: string | null;
}

/** Plain-language description of what the task is waiting on, derived only from API fields. */
export function describeTask(task: TaskCard): Callout {
  const sha = shortSha(task.expected_sha);
  const resolution = resolutionLabel(task.resolution);
  if (task.paused) {
    return { tone: "warn", Icon: PauseCircle, title: "Paused", body: "Nothing new starts for this PR until you resume it." };
  }
  if (task.pending_action === "analyze") {
    return { tone: "warn", Icon: Hand, title: `CI failed on ${sha} — waiting for “Analyze now”`, body: "Auto Analyze is off, so the diagnosis starts when you ask for it." };
  }
  if (task.pending_action === "remediate") {
    return { tone: "warn", Icon: Hand, title: "Diagnosis ready — waiting for “Start remediation”", body: "Auto Remediate is off. Review the plan, then start the fix." };
  }
  if (task.pending_action === "push") {
    return { tone: "warn", Icon: Hand, title: "Validated fix ready — approval required before pushing", body: "Auto Push is off. The commit stays local until you approve it." };
  }
  switch (task.state) {
    case "NEW":
      return { tone: "info", Icon: Clock, title: "Registered", body: task.activity ?? `The first GitHub Actions check on ${sha} is due shortly.` };
    case "WAITING_CI":
      return { tone: "info", Icon: Clock, title: `Waiting for GitHub Actions on ${sha}`, body: task.activity };
    case "VALIDATING":
      return { tone: "info", Icon: Clock, title: `Fix pushed — waiting for GitHub Actions on ${sha}`, body: task.activity };
    case "ANALYZING":
      return { tone: "info", Icon: Clock, title: "Analysis queued", body: task.activity ?? "Starts as soon as an agent slot is free." };
    case "TODO":
      return { tone: "info", Icon: Clock, title: "Fix planned", body: task.activity ?? "Remediation starts when an agent slot is free." };
    case "IN_PROGRESS":
      return { tone: "info", Icon: Clock, title: "Remediation in progress", body: task.activity };
    case "NEEDS_REVIEW":
      return { tone: "warn", Icon: AlertTriangle, title: `Needs a human${resolution ? `: ${resolution}` : ""}`, body: task.last_error };
    case "FAILED":
      return { tone: "bad", Icon: XCircle, title: resolution ?? "Failed", body: task.last_error };
    case "DONE":
      return {
        tone: "ok",
        Icon: CheckCircle2,
        title: resolution ?? "Done",
        body: task.resolution === "remediated" ? `Required checks passed on ${sha}.` : null,
      };
    default:
      return { tone: "info", Icon: Clock, title: task.state, body: task.activity };
  }
}
