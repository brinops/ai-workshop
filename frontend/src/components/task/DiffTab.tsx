import { CheckCircle2, ShieldAlert, ShieldCheck, XCircle } from "lucide-react";
import { useState } from "react";
import { DiffView } from "@/components/common/DiffView";
import { Sha } from "@/components/common/StatusBits";
import { Badge } from "@/components/ui/badge";
import { absoluteTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { RemediationOut, TaskCard } from "@/services/api";

const PUSH_TONE: Record<string, "success" | "warning" | "danger" | "info" | "neutral"> = {
  pushed: "success",
  approved: "info",
  pending_approval: "warning",
  rejected: "danger",
  failed: "danger",
  discarded: "neutral",
};

export function PushStatusBadge({ status }: { status: string }) {
  return <Badge tone={PUSH_TONE[status] ?? "neutral"}>push: {status.replace(/_/g, " ")}</Badge>;
}

export function RemediationSummary({ rem }: { rem: RemediationOut }) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-medium">Attempt {rem.attempt}</span>
        <span className="text-faint">on</span> <Sha sha={rem.base_sha} label="base" />
        {rem.commit_sha ? (
          <>
            <span className="text-faint">→ commit</span> <Sha sha={rem.commit_sha} label="commit" />
          </>
        ) : (
          <span className="text-faint">no commit</span>
        )}
        <PushStatusBadge status={rem.push_status} />
        {rem.pushed_at && <span className="text-xs text-faint">pushed {absoluteTime(rem.pushed_at)}</span>}
      </div>
      {rem.summary && <p className="max-w-[75ch] text-fg/95">{rem.summary}</p>}
      <div className="flex flex-wrap gap-2">
        <span
          className={cn(
            "inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-sm",
            rem.scope_ok ? "border-ok/35 text-ok" : "border-bad/40 text-bad",
          )}
        >
          {rem.scope_ok ? <ShieldCheck className="size-4" aria-hidden /> : <ShieldAlert className="size-4" aria-hidden />}
          Scope check {rem.scope_ok ? "passed" : "failed"}
        </span>
        <span
          className={cn(
            "inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-sm",
            rem.validation_passed ? "border-ok/35 text-ok" : "border-bad/40 text-bad",
          )}
        >
          {rem.validation_passed ? <CheckCircle2 className="size-4" aria-hidden /> : <XCircle className="size-4" aria-hidden />}
          Local validation {rem.validation_passed ? "passed" : "failed"}
        </span>
      </div>
      {rem.scope_violations.length > 0 && (
        <ul className="ml-5 list-disc text-sm text-bad">
          {rem.scope_violations.map((v, i) => (
            <li key={i}>{v}</li>
          ))}
        </ul>
      )}
      {rem.push_error && <p className="text-sm text-bad">Push error: {rem.push_error}</p>}
    </div>
  );
}

export function DiffTab({ remediations, task }: { remediations: RemediationOut[]; task: TaskCard }) {
  const [selected, setSelected] = useState<number | null>(null);
  if (remediations.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-line-strong px-4 py-8 text-center">
        <p className="font-medium">No fix yet</p>
        <p className="mt-1 text-sm text-muted">
          {task.state === "IN_PROGRESS"
            ? "The Remediation Subagent is working in an isolated worktree — the diff shows up when it finishes."
            : "A diff appears here after the Remediation Subagent proposes a fix."}
        </p>
      </div>
    );
  }
  const rem = remediations.find((r) => r.id === selected) ?? remediations[remediations.length - 1];
  return (
    <div className="flex flex-col gap-4">
      {remediations.length > 1 && (
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Remediation attempts">
          {remediations.map((r) => (
            <button
              key={r.id}
              onClick={() => setSelected(r.id)}
              aria-pressed={r.id === rem.id}
              className={cn(
                "rounded-md border px-2.5 py-1 text-sm",
                r.id === rem.id ? "border-accent bg-accent/10 text-fg" : "border-line text-muted hover:text-fg",
              )}
            >
              Attempt {r.attempt}
            </button>
          ))}
        </div>
      )}
      <RemediationSummary rem={rem} />
      {rem.files.length > 0 && (
        <table className="w-full overflow-hidden rounded-md border border-line text-sm">
          <thead className="bg-raised text-left text-xs text-muted">
            <tr>
              <th className="px-3 py-1.5 font-medium">File</th>
              <th className="px-3 py-1.5 font-medium">Status</th>
              <th className="px-3 py-1.5 text-right font-medium">Lines</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {rem.files.map((f) => (
              <tr key={f.path}>
                <td className="px-3 py-1.5 font-mono text-[0.82rem]">{f.path}</td>
                <td className="px-3 py-1.5 font-mono text-xs text-muted">{f.status}</td>
                <td className="px-3 py-1.5 text-right font-mono text-xs">
                  <span className="text-ok">+{f.added}</span> <span className="text-bad">−{f.removed}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <DiffView diff={rem.diff} />
    </div>
  );
}
