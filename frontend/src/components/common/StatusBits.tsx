import {
  Ban,
  CheckCircle2,
  CircleDashed,
  CircleSlash,
  Hand,
  Loader2,
  PauseCircle,
  XCircle,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { humanize, shortSha } from "@/lib/format";
import { PENDING_ACTION_COPY, stateLabel, stateTone } from "@/lib/states";

export function StateBadge({ state, className }: { state: string; className?: string }) {
  return (
    <Badge tone={stateTone(state)} className={cn("font-mono tracking-tight", className)} title={stateLabel(state)}>
      {state}
    </Badge>
  );
}

const CLASSIFICATION_TONE: Record<string, "amber" | "violet" | "cyan" | "gray"> = {
  SYNTAX_ERROR: "amber",
  SCHEMA_VIOLATION: "violet",
  LOGICAL_CONFIGURATION_ERROR: "cyan",
  NON_REMEDIABLE: "gray",
  UNKNOWN: "gray",
};

const CLASSIFICATION_SHORT: Record<string, string> = {
  SYNTAX_ERROR: "Syntax error",
  SCHEMA_VIOLATION: "Schema violation",
  LOGICAL_CONFIGURATION_ERROR: "Logical config error",
  NON_REMEDIABLE: "Non-remediable",
  UNKNOWN: "Unknown",
};

export function ClassificationChip({
  value,
  confidence,
  className,
}: {
  value: string | null | undefined;
  confidence?: number | null;
  className?: string;
}) {
  if (!value) return null;
  const tone = CLASSIFICATION_TONE[value] ?? "gray";
  return (
    <Badge tone={tone} className={className} title={value}>
      <span className="size-1.5 rounded-[2px] bg-current" aria-hidden />
      {CLASSIFICATION_SHORT[value] ?? humanize(value)}
      {confidence !== null && confidence !== undefined && (
        <span className="opacity-70">· {Math.round(confidence * 100)}%</span>
      )}
    </Badge>
  );
}

export function CIStatusDot({ status, className }: { status: string | null | undefined; className?: string }) {
  const color =
    status === "success"
      ? "bg-ok"
      : status === "failure"
        ? "bg-bad"
        : status === "pending"
          ? "bg-amber animate-pulse-dot"
          : "bg-gray";
  return <span className={cn("inline-block size-2 shrink-0 rounded-full", color, className)} aria-hidden />;
}

const CI_TEXT: Record<string, string> = {
  success: "CI passed",
  failure: "CI failed",
  pending: "CI running",
  cancelled: "CI cancelled",
  skipped: "CI skipped",
  missing: "Check missing",
};

export function CIStatus({ status, sha, className }: { status: string | null | undefined; sha?: string; className?: string }) {
  if (!status) {
    return (
      <span className={cn("inline-flex items-center gap-1.5 text-xs text-faint", className)}>
        <CircleDashed className="size-3.5" aria-hidden />
        No CI result yet
      </span>
    );
  }
  const Icon =
    status === "success" ? CheckCircle2 : status === "failure" ? XCircle : status === "pending" ? Loader2 : CircleSlash;
  const color =
    status === "success" ? "text-ok" : status === "failure" ? "text-bad" : status === "pending" ? "text-amber" : "text-gray";
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-xs", color, className)}>
      {status === "pending" ? <CIStatusDot status="pending" /> : <Icon className="size-3.5" aria-hidden />}
      {CI_TEXT[status] ?? humanize(status)}
      {sha && <span className="font-mono text-faint">{shortSha(sha)}</span>}
    </span>
  );
}

export function VerdictBadge({ verdict }: { verdict: string }) {
  const tone =
    verdict === "success" ? "success" : verdict === "failure" ? "danger" : verdict === "pending" || verdict === "missing" ? "amber" : "gray";
  const Icon =
    verdict === "success" ? CheckCircle2 : verdict === "failure" ? XCircle : verdict === "pending" ? Loader2 : verdict === "cancelled" ? Ban : CircleDashed;
  return (
    <Badge tone={tone}>
      <Icon className={cn(verdict === "pending" && "animate-spin")} aria-hidden />
      {verdict}
    </Badge>
  );
}

export function PausedBadge() {
  return (
    <Badge tone="warning">
      <PauseCircle aria-hidden /> Paused
    </Badge>
  );
}

export function PendingActionBadge({ pending }: { pending: string }) {
  const copy = PENDING_ACTION_COPY[pending];
  return (
    <Badge tone="warning" className="border-dashed">
      <Hand aria-hidden />
      {copy?.label ?? `Awaiting ${pending}`}
    </Badge>
  );
}

/**
 * Live "agent working" indicator. Only rendered when the API reports `agent_running`;
 * the text is the backend's own `activity` string.
 */
export function AgentWorking({
  activity,
  size = "sm",
  className,
}: {
  activity: string | null;
  size?: "sm" | "lg";
  className?: string;
}) {
  return (
    <div
      className={cn(
        "relative flex items-start gap-2 overflow-hidden rounded-md border border-accent/30 bg-accent/[0.07]",
        size === "lg" ? "px-3.5 py-2.5 text-base" : "px-2 py-1 text-xs",
        className,
      )}
      role="status"
      aria-live="polite"
    >
      <span
        className="pointer-events-none absolute inset-y-0 left-0 w-1/3 animate-sweep bg-gradient-to-r from-transparent via-accent/15 to-transparent"
        aria-hidden
      />
      <span className={cn("relative mt-[0.2em] flex shrink-0 items-end gap-[2px]", size === "lg" ? "h-4" : "h-3")} aria-hidden>
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="w-[3px] animate-pulse-dot rounded-sm bg-accent"
            style={{ height: "100%", animationDelay: `${i * 0.18}s` }}
          />
        ))}
      </span>
      <span className={cn("relative min-w-0 text-accent", size === "sm" ? "line-clamp-2" : "")}>
        <span className="font-medium">Agent working</span>
        {activity && <span className="text-fg/80"> — {activity}</span>}
      </span>
    </div>
  );
}

export function Sha({ sha, label }: { sha: string | null | undefined; label?: string }) {
  if (!sha) return <span className="text-faint">—</span>;
  return (
    <Tooltip content={<span className="font-mono">{sha}</span>}>
      <code className="rounded bg-raised px-1 py-px font-mono text-[0.85em] text-fg/90" aria-label={label ? `${label} ${sha}` : sha} tabIndex={0}>
        {shortSha(sha)}
      </code>
    </Tooltip>
  );
}
