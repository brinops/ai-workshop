import { ExternalLink, GitBranch } from "lucide-react";
import { Link } from "react-router-dom";
import { DiffView } from "@/components/common/DiffView";
import { PipelineStrip } from "@/components/common/Pipeline";
import { CIStatus, ClassificationChip, PendingActionBadge, StateBadge } from "@/components/common/StatusBits";
import { PushStatusBadge } from "@/components/task/DiffTab";
import { StatusCallout } from "@/components/task/StatusCallout";
import { TaskActions } from "@/components/task/TaskActions";
import { Timeline } from "@/components/task/TimelineTab";
import { useTask } from "@/hooks/queries";
import { shortSha } from "@/lib/format";
import { latestDiagnosis, latestRemediation } from "@/lib/selectors";
import { stateLabel } from "@/lib/states";
import type { TaskCard } from "@/services/api";

/** Presentation-mode focus panel for the most relevant task (data straight from the API). */
export function Spotlight({ card }: { card: TaskCard }) {
  const { data } = useTask(card.id);
  const task = data?.task ?? card;
  const diag = data ? latestDiagnosis(data) : null;
  const rem = data ? latestRemediation(data) : null;

  return (
    <section className="flex flex-col gap-5 rounded-xl border border-line-strong bg-panel p-6" aria-label="Spotlight task">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-2 font-mono text-sm text-muted">
            {task.repo} #{task.pr_number}
            <span className="inline-flex items-center gap-1">
              <GitBranch className="size-3.5" aria-hidden />
              {task.head_branch} @{shortSha(task.expected_sha)}
            </span>
          </p>
          <h2 className="mt-1 text-2xl font-semibold leading-tight tracking-tight">
            <Link to={`/tasks/${task.id}`} className="hover:underline">
              {task.title || `Pull request #${task.pr_number}`}
            </Link>
          </h2>
        </div>
        <div className="flex flex-col items-end gap-2">
          <div className="flex items-center gap-2">
            <StateBadge state={task.state} className="text-sm" />
            <span className="text-lg font-medium">{stateLabel(task.state)}</span>
          </div>
          <a href={task.pr_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-sm text-accent hover:underline">
            Open PR <ExternalLink className="size-3.5" aria-hidden />
          </a>
        </div>
      </div>

      <PipelineStrip state={task.state} resolution={task.resolution} agentRunning={task.agent_running} size="lg" />
      <StatusCallout task={task} size="lg" />

      <div className="flex flex-wrap items-center gap-2">
        <CIStatus status={task.ci_status} sha={task.expected_sha} className="text-sm" />
        <ClassificationChip value={task.classification} confidence={task.confidence} className="text-sm" />
        {task.pending_action && <PendingActionBadge pending={task.pending_action} />}
        {rem && <PushStatusBadge status={rem.push_status} />}
      </div>
      {data && data.actions.some((a) => a === "approve_push" || a === "analyze" || a === "start_remediation") && (
        <TaskActions taskId={task.id} actions={data.actions.filter((a) => a === "approve_push" || a === "analyze" || a === "start_remediation")} />
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          {(diag?.data.analysis?.root_cause ?? task.root_cause) && (
            <div>
              <h3 className="text-sm font-semibold text-muted">Root cause</h3>
              <p className="mt-1 leading-relaxed">{diag?.data.analysis?.root_cause ?? task.root_cause}</p>
            </div>
          )}
          <div>
            <h3 className="mb-2 text-sm font-semibold text-muted">Latest activity</h3>
            {data ? <Timeline events={data.events} limit={6} compact /> : <p className="text-sm text-muted">Loading…</p>}
          </div>
        </div>
        <div className="min-w-0">
          <h3 className="mb-2 text-sm font-semibold text-muted">The fix</h3>
          {rem && rem.diff.trim() ? (
            <DiffView diff={rem.diff} maxHeight="26rem" />
          ) : (
            <p className="rounded-md border border-dashed border-line-strong px-4 py-8 text-center text-muted">
              {task.state === "IN_PROGRESS" ? "The Remediation Subagent is preparing a fix…" : "No fix proposed yet."}
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
