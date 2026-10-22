import type { ActionName } from "@/services/api";

export interface ActionMeta {
  label: string;
  pastTense: string;
  description: string;
  confirm?: { title: string; body: string; confirmLabel: string };
}

export const ACTION_META: Record<ActionName, ActionMeta> = {
  analyze: { label: "Analyze now", pastTense: "Analysis queued", description: "Run the Analysis Skill on the failed CI" },
  start_remediation: {
    label: "Start remediation",
    pastTense: "Remediation queued",
    description: "Let the Remediation Subagent fix the chart in an isolated worktree",
  },
  approve_push: {
    label: "Approve push",
    pastTense: "Push approved",
    description: "Push the validated fix commit to the PR branch",
  },
  retry: { label: "Retry", pastTense: "Retry scheduled", description: "Reset attempts and re-check CI on the PR head" },
  pause: { label: "Pause", pastTense: "Paused", description: "Let the running agent finish, start nothing new" },
  resume: { label: "Resume", pastTense: "Resumed", description: "Continue automation for this task" },
  cancel: {
    label: "Cancel",
    pastTense: "Cancelled",
    description: "Stop work on this PR and move it to Failed",
    confirm: {
      title: "Cancel this task?",
      body: "Any running agent is stopped and the task moves to FAILED (resolution: cancelled). You can use Retry later.",
      confirmLabel: "Cancel task",
    },
  },
  mark_review: {
    label: "Mark for review",
    pastTense: "Marked for review",
    description: "Hand the task to a human; stops any running agent",
  },
};

/** Display order of manual controls. */
export const ACTION_ORDER: ActionName[] = [
  "approve_push",
  "analyze",
  "start_remediation",
  "retry",
  "pause",
  "resume",
  "mark_review",
  "cancel",
];
