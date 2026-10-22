import { AlertTriangle, GitBranch, Hand, Rocket, Sparkles, Wrench } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import {
  AgentWorking,
  CIStatus,
  ClassificationChip,
  PausedBadge,
  PendingActionBadge,
  StateBadge,
} from "@/components/common/StatusBits";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useRunAction } from "@/hooks/useRunAction";
import { relativeTime, shortSha } from "@/lib/format";
import { PENDING_ACTION_COPY, resolutionLabel } from "@/lib/states";
import { cn } from "@/lib/utils";
import type { TaskCard } from "@/services/api";

const INLINE_ICON = { analyze: Sparkles, start_remediation: Wrench, approve_push: Rocket } as const;
const INLINE_LABEL = { analyze: "Analyze now", start_remediation: "Start remediation", approve_push: "Approve push" } as const;

function InlineAction({ task }: { task: TaskCard }) {
  const { run, pending } = useRunAction(task.id);
  const copy = task.pending_action ? PENDING_ACTION_COPY[task.pending_action] : undefined;
  if (!copy || task.paused) return null;
  const Icon = INLINE_ICON[copy.action];
  return (
    <Button
      size="sm"
      variant={copy.action === "approve_push" ? "primary" : "default"}
      className="relative z-10"
      disabled={pending !== null}
      onClick={() => run(copy.action)}
      aria-label={`${INLINE_LABEL[copy.action]} for PR #${task.pr_number}`}
    >
      <Icon /> {INLINE_LABEL[copy.action]}
    </Button>
  );
}

export function TaskCardView({ task, now, selected }: { task: TaskCard; now: number; selected: boolean }) {
  // Flash the card briefly whenever the backend reports a change (derived-state pattern).
  const [prevUpdated, setPrevUpdated] = useState(task.updated_at);
  const [flashKey, setFlashKey] = useState(0);
  if (prevUpdated !== task.updated_at) {
    setPrevUpdated(task.updated_at);
    setFlashKey((k) => k + 1);
  }

  const resolution = resolutionLabel(task.resolution);
  const terminalProblem = task.state === "FAILED" || task.state === "NEEDS_REVIEW";

  return (
    <article
      className={cn(
        "group relative animate-card-in rounded-lg border bg-panel p-3 transition-[border-color,background-color] duration-300",
        "hover:border-line-strong hover:bg-raised/60 focus-within:border-accent/60",
        task.agent_running && "border-accent/40",
        task.pending_action && !task.agent_running && "border-warn/40",
        selected && "border-accent ring-1 ring-accent/40",
        !task.agent_running && !task.pending_action && !selected && "border-line",
      )}
      aria-label={`PR #${task.pr_number}: ${task.title}`}
    >
      {flashKey > 0 && <span key={flashKey} className="pointer-events-none absolute inset-0 animate-flash rounded-lg" aria-hidden />}

      <div className="flex items-start justify-between gap-2">
        <p className="min-w-0 truncate font-mono text-[0.72rem] text-muted" title={task.repo}>
          {task.repo.split("/").pop()} <span className="text-fg/80">#{task.pr_number}</span>
        </p>
        <StateBadge state={task.state} />
      </div>

      <h3 className="mt-1 line-clamp-2 text-[0.92rem] font-medium leading-snug">
        <Link
          to={`/tasks/${task.id}`}
          className="after:absolute after:inset-0 after:rounded-lg focus-visible:outline-none"
        >
          {task.title || `Pull request #${task.pr_number}`}
        </Link>
      </h3>

      <p className="mt-1.5 flex min-w-0 items-center gap-1.5 text-xs text-muted">
        <GitBranch className="size-3.5 shrink-0" aria-hidden />
        <span className="truncate font-mono">{task.head_branch}</span>
        <span className="shrink-0 font-mono text-faint">@{shortSha(task.expected_sha)}</span>
      </p>

      <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
        <CIStatus status={task.ci_status} className="mr-1" />
        <ClassificationChip value={task.classification} />
        {task.attempt > 0 && (
          <Badge tone="neutral" title="Remediation attempts used">
            attempt {task.attempt}/{task.max_attempts}
          </Badge>
        )}
        {task.paused && <PausedBadge />}
        {task.pending_action && <PendingActionBadge pending={task.pending_action} />}
      </div>

      {task.agent_running ? (
        <AgentWorking activity={task.activity} className="mt-2.5" />
      ) : task.activity ? (
        <p className="mt-2.5 line-clamp-2 text-xs text-muted">{task.activity}</p>
      ) : null}

      {terminalProblem && (resolution || task.last_error) && (
        <p className="mt-2 flex items-start gap-1.5 text-xs text-warn">
          <AlertTriangle className="mt-px size-3.5 shrink-0" aria-hidden />
          <span className="line-clamp-2">
            {resolution}
            {task.last_error && <span className="text-muted"> — {task.last_error}</span>}
          </span>
        </p>
      )}
      {task.state === "DONE" && resolution && <p className="mt-2 text-xs text-ok">{resolution}</p>}

      <div className="mt-2.5 flex items-center justify-between gap-2">
        <time className="text-[0.7rem] text-faint" dateTime={task.updated_at}>
          updated {relativeTime(task.updated_at, now)}
        </time>
        <InlineAction task={task} />
        {task.pending_action && task.paused && (
          <span className="inline-flex items-center gap-1 text-[0.7rem] text-faint">
            <Hand className="size-3" aria-hidden /> resume to act
          </span>
        )}
      </div>
    </article>
  );
}
