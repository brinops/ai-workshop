import { ArrowRight, ExternalLink, GitBranch } from "lucide-react";
import { CIStatus, ClassificationChip, PausedBadge, PendingActionBadge, Sha, StateBadge } from "@/components/common/StatusBits";
import { Badge } from "@/components/ui/badge";
import { SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { COLUMNS, resolutionLabel, stateLabel } from "@/lib/states";
import type { TaskCard } from "@/services/api";

export function TaskHeader({ task }: { task: TaskCard }) {
  const column = COLUMNS.find((c) => c.id === task.column)?.title ?? task.column;
  const resolution = resolutionLabel(task.resolution);
  const shaDiffers = task.head_sha !== task.expected_sha;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2 pr-10 text-sm text-muted">
        <span className="font-mono">{task.repo}</span>
        <a
          href={task.pr_url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 rounded px-1 text-accent hover:underline"
        >
          PR #{task.pr_number} on GitHub <ExternalLink className="size-3.5" aria-hidden />
        </a>
        {task.author && <span>by {task.author}</span>}
        <span className="text-faint">task #{task.id} · via {task.source}</span>
      </div>
      <SheetTitle className="pr-10 text-xl font-semibold leading-tight tracking-tight">
        {task.title || `Pull request #${task.pr_number}`}
      </SheetTitle>
      <SheetDescription className="sr-only">Remediation details for pull request #{task.pr_number}</SheetDescription>

      <div className="flex flex-wrap items-center gap-2">
        <StateBadge state={task.state} />
        <span className="text-sm text-muted">
          {stateLabel(task.state)} <span className="text-faint">in {column}</span>
        </span>
        {resolution && <Badge tone={task.resolution === "remediated" || task.resolution === "passed_without_remediation" ? "success" : "warning"}>{resolution}</Badge>}
        <ClassificationChip value={task.classification} confidence={task.confidence} />
        <CIStatus status={task.ci_status} />
        {task.attempt > 0 && <Badge>attempt {task.attempt}/{task.max_attempts}</Badge>}
        {task.paused && <PausedBadge />}
        {task.pending_action && <PendingActionBadge pending={task.pending_action} />}
      </div>

      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm sm:grid-cols-[auto_1fr_auto_1fr]">
        <dt className="text-faint">Branch</dt>
        <dd className="flex min-w-0 items-center gap-1.5 font-mono text-[0.85rem]">
          <GitBranch className="size-3.5 shrink-0 text-faint" aria-hidden />
          <span className="truncate">{task.head_branch}</span>
          <ArrowRight className="size-3.5 shrink-0 text-faint" aria-label="into" />
          <span className="truncate">{task.base_branch}</span>
        </dd>
        <dt className="text-faint">Commits</dt>
        <dd className="flex flex-wrap items-center gap-1.5 text-[0.85rem]">
          <span className="text-faint">head</span> <Sha sha={task.head_sha} label="head" />
          <span className="text-faint">acting on</span> <Sha sha={task.expected_sha} label="expected" />
          {shaDiffers && <Badge tone="amber">fix pending on CI</Badge>}
        </dd>
      </dl>
    </div>
  );
}
