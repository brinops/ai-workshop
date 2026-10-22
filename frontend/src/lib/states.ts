import type { ColumnId, TaskCard, TaskState } from "@/services/api";

/** Mirror of backend COLUMN_OF (backend/app/models/__init__.py). */
export const COLUMN_OF: Record<TaskState, ColumnId> = {
  NEW: "NEW",
  WAITING_CI: "NEW",
  ANALYZING: "NEW",
  TODO: "TODO",
  NEEDS_REVIEW: "TODO",
  IN_PROGRESS: "IN_PROGRESS",
  VALIDATING: "IN_PROGRESS",
  DONE: "DONE",
  FAILED: "DONE",
};

export const COLUMNS: { id: ColumnId; title: string; hint: string }[] = [
  { id: "NEW", title: "New", hint: "Registered PRs waiting on CI or being analyzed" },
  { id: "TODO", title: "To do", hint: "Diagnosed — waiting to be fixed or reviewed" },
  { id: "IN_PROGRESS", title: "In progress", hint: "Agent fixing, validating or waiting for CI on the fix" },
  { id: "DONE", title: "Done", hint: "Remediated, passed, or stopped" },
];

export function columnOf(state: string): ColumnId {
  return COLUMN_OF[state as TaskState] ?? "NEW";
}

export function statesInColumn(column: ColumnId): TaskState[] {
  return (Object.keys(COLUMN_OF) as TaskState[]).filter((s) => COLUMN_OF[s] === column);
}

export const STATE_LABEL: Record<TaskState, string> = {
  NEW: "New",
  WAITING_CI: "Waiting for CI",
  ANALYZING: "Analyzing",
  TODO: "Fix planned",
  NEEDS_REVIEW: "Needs review",
  IN_PROGRESS: "Remediating",
  VALIDATING: "Validating on CI",
  DONE: "Done",
  FAILED: "Failed",
};

export function stateLabel(state: string): string {
  return STATE_LABEL[state as TaskState] ?? state;
}

export type Tone = "neutral" | "info" | "accent" | "success" | "warning" | "danger" | "violet" | "cyan" | "amber";

export const STATE_TONE: Record<TaskState, Tone> = {
  NEW: "neutral",
  WAITING_CI: "amber",
  ANALYZING: "accent",
  TODO: "info",
  NEEDS_REVIEW: "warning",
  IN_PROGRESS: "accent",
  VALIDATING: "amber",
  DONE: "success",
  FAILED: "danger",
};

export function stateTone(state: string): Tone {
  return STATE_TONE[state as TaskState] ?? "neutral";
}

/* ------------------------------------------------------------------ pipeline */

export type PipelineStage = "detection" | "reasoning" | "repair" | "validation" | "visibility";

export const PIPELINE: { id: PipelineStage; label: string; detail: string }[] = [
  { id: "detection", label: "Detection", detail: "PR registered, GitHub Actions polled" },
  { id: "reasoning", label: "Reasoning", detail: "Analysis Skill diagnoses the failure" },
  { id: "repair", label: "Repair", detail: "Remediation Subagent fixes in a worktree" },
  { id: "validation", label: "Validation", detail: "Local checks, push, CI re-run" },
  { id: "visibility", label: "Visibility", detail: "Board + Slack notification" },
];

export function pipelineStageOf(state: string): PipelineStage {
  switch (state as TaskState) {
    case "NEW":
    case "WAITING_CI":
      return "detection";
    case "ANALYZING":
    case "TODO":
      return "reasoning";
    case "IN_PROGRESS":
      return "repair";
    case "VALIDATING":
      return "validation";
    default:
      return "visibility";
  }
}

export type StageStatus = "done" | "active" | "stopped" | "idle";

/**
 * Per-stage status for the pipeline strip, derived only from state + resolution.
 * Stages are marked done only when the state proves they happened.
 */
export function pipelineStatuses(state: string | null, resolution?: string | null): Record<PipelineStage, StageStatus> {
  const out = Object.fromEntries(PIPELINE.map((p) => [p.id, "idle"])) as Record<PipelineStage, StageStatus>;
  if (!state) return out;
  if (state === "NEEDS_REVIEW" || state === "FAILED") {
    out.visibility = "stopped";
    return out;
  }
  if (state === "DONE") {
    if (resolution === "remediated") {
      for (const p of PIPELINE) out[p.id] = "done";
    } else {
      out.detection = "done";
      out.visibility = "done";
    }
    return out;
  }
  const current = pipelineStageOf(state);
  const idx = PIPELINE.findIndex((p) => p.id === current);
  PIPELINE.forEach((p, i) => {
    out[p.id] = i < idx ? "done" : i === idx ? "active" : "idle";
  });
  return out;
}

export function isActive(task: Pick<TaskCard, "state">): boolean {
  return task.state !== "DONE" && task.state !== "FAILED";
}

/** Most recently updated non-terminal task; falls back to the most recent task overall. */
export function pickSpotlight(tasks: TaskCard[]): TaskCard | null {
  if (tasks.length === 0) return null;
  const sorted = [...tasks].sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  const running = sorted.find((t) => t.agent_running);
  return running ?? sorted.find(isActive) ?? sorted[0];
}

export const PENDING_ACTION_COPY: Record<string, { label: string; action: "analyze" | "start_remediation" | "approve_push" }> = {
  analyze: { label: "Awaiting “Analyze Now”", action: "analyze" },
  remediate: { label: "Awaiting “Start Remediation”", action: "start_remediation" },
  push: { label: "Awaiting push approval", action: "approve_push" },
};

export const RESOLUTION_LABEL: Record<string, string> = {
  remediated: "Remediated",
  passed_without_remediation: "Passed without remediation",
  not_auto_remediable: "Not auto-remediable",
  remediation_rejected: "Fix rejected",
  attempts_exhausted: "Attempts exhausted",
  analysis_failed: "Analysis failed",
  push_failed: "Push failed",
  ci_timeout: "CI timed out",
  cancelled: "Cancelled",
  manual_review: "Manual review",
  internal_error: "Internal error",
};

export function resolutionLabel(r: string | null | undefined): string | null {
  if (!r) return null;
  return RESOLUTION_LABEL[r] ?? r.replace(/_/g, " ");
}
