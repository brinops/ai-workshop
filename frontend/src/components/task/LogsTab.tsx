import { AlertOctagon, ArrowDownToLine, Bot, ChevronDown, ChevronRight, Flag, MessageSquareText, Terminal, Wrench } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useNow } from "@/hooks/useNow";
import { useRunLogs } from "@/hooks/useRunLogs";
import { clockTime, durationBetween, formatCost } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { AgentRunOut, LogLineOut } from "@/services/api";

function runTone(status: string) {
  if (status === "running") return "accent" as const;
  if (status === "succeeded" || status === "success" || status === "completed") return "success" as const;
  if (status === "cancelled" || status === "interrupted") return "gray" as const;
  return "danger" as const;
}

function LogLineBody({ line }: { line: LogLineOut }) {
  const time = <span className="w-[4.75rem] shrink-0 select-none pt-px font-mono text-[0.7rem] text-faint tabular-nums">{clockTime(line.ts)}</span>;
  switch (line.kind) {
    case "tool_use": {
      const [tool, ...rest] = line.text.split(" · ");
      return (
        <div className="flex gap-2 py-1">
          {time}
          <Wrench className="mt-0.5 size-3.5 shrink-0 text-accent" aria-label="tool call" />
          <p className="min-w-0 font-mono text-[0.8rem]">
            <span className="font-semibold text-accent">{tool}</span>
            {rest.length > 0 && <span className="text-fg/85"> {rest.join(" · ")}</span>}
          </p>
        </div>
      );
    }
    case "tool_result":
      return (
        <div className="flex gap-2 py-0.5">
          {time}
          <ChevronRight className="mt-0.5 size-3.5 shrink-0 text-faint" aria-label="tool result" />
          <pre className="min-w-0 whitespace-pre-wrap break-words font-mono text-[0.75rem] text-faint">{line.text}</pre>
        </div>
      );
    case "text":
      return (
        <div className="flex gap-2 py-1.5">
          {time}
          <MessageSquareText className="mt-0.5 size-3.5 shrink-0 text-fg/70" aria-label="assistant" />
          <p className="min-w-0 whitespace-pre-wrap text-[0.88rem] leading-relaxed text-fg">{line.text}</p>
        </div>
      );
    case "result":
      return (
        <div className="my-1.5 flex gap-2 rounded-md border border-ok/30 bg-ok/[0.07] px-2 py-2">
          {time}
          <Flag className="mt-0.5 size-3.5 shrink-0 text-ok" aria-label="result" />
          <p className="min-w-0 whitespace-pre-wrap text-[0.85rem] font-medium text-ok">{line.text}</p>
        </div>
      );
    case "stderr":
      return (
        <div className="flex gap-2 py-0.5">
          {time}
          <AlertOctagon className="mt-0.5 size-3.5 shrink-0 text-bad" aria-label="stderr" />
          <pre className="min-w-0 whitespace-pre-wrap break-words font-mono text-[0.75rem] text-bad/90">{line.text}</pre>
        </div>
      );
    default:
      return (
        <div className="flex gap-2 py-0.5">
          {time}
          <Terminal className="mt-0.5 size-3.5 shrink-0 text-muted" aria-label="system" />
          <p className="min-w-0 whitespace-pre-wrap font-mono text-[0.75rem] text-muted">{line.text}</p>
        </div>
      );
  }
}

/** A log line; lines carrying the full tool input/output expand on click. */
function LogLine({ line }: { line: LogLineOut }) {
  const [open, setOpen] = useState(false);
  if (!line.detail) return <LogLineBody line={line} />;
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        title={open ? "Collapse" : "Show full content"}
        className="group -mx-1 flex w-[calc(100%+0.5rem)] items-start rounded px-1 text-left hover:bg-panel focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      >
        <div className="min-w-0 flex-1">
          <LogLineBody line={line} />
        </div>
        <ChevronDown
          className={cn("mt-1.5 size-3.5 shrink-0 text-faint transition-transform group-hover:text-muted", !open && "-rotate-90")}
          aria-hidden
        />
      </button>
      {open && (
        <pre className="mb-1.5 ml-[6.6rem] max-h-96 overflow-auto rounded border border-line bg-panel px-3 py-2 font-mono text-[0.75rem] leading-relaxed whitespace-pre-wrap break-words text-fg/90 scroll-thin">
          {line.detail}
        </pre>
      )}
    </div>
  );
}

export function LogStream({ taskId, run, height = "32rem" }: { taskId: number; run: AgentRunOut; height?: string }) {
  const { lines, loading, error } = useRunLogs(taskId, run.id);
  const scroller = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const [detached, setDetached] = useState(false);

  useEffect(() => {
    const el = scroller.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [lines.length]);

  const onScroll = () => {
    const el = scroller.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    stick.current = atBottom;
    setDetached(!atBottom);
  };

  return (
    <div className="relative">
      <div
        ref={scroller}
        onScroll={onScroll}
        className="overflow-y-auto rounded-md border border-line bg-sunken px-3 py-2 scroll-thin"
        style={{ height }}
        role="log"
        aria-live={run.status === "running" ? "polite" : "off"}
        aria-label={`Log of ${run.kind} run #${run.id}`}
      >
        {loading && lines.length === 0 && <p className="py-4 text-sm text-muted">Loading log…</p>}
        {error && <p className="py-4 text-sm text-bad">Couldn't load the log: {error}</p>}
        {!loading && !error && lines.length === 0 && (
          <p className="py-4 text-sm text-muted">
            {run.status === "running" ? "The agent has started — output streams in as it works." : "This run produced no log output."}
          </p>
        )}
        {lines.map((l) => (
          <LogLine key={l.id} line={l} />
        ))}
        {run.status === "running" && lines.length > 0 && (
          <div className="flex items-center gap-2 py-1.5 text-xs text-accent">
            <span className="size-1.5 animate-pulse-dot rounded-full bg-accent" aria-hidden /> streaming
          </div>
        )}
      </div>
      {detached && (
        <Button
          size="sm"
          className="absolute bottom-3 right-3"
          onClick={() => {
            const el = scroller.current;
            if (el) el.scrollTop = el.scrollHeight;
            stick.current = true;
            setDetached(false);
          }}
        >
          <ArrowDownToLine /> Jump to latest
        </Button>
      )}
    </div>
  );
}

export function LogsTab({ taskId, runs }: { taskId: number; runs: AgentRunOut[] }) {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const now = useNow(1000);
  if (runs.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-line-strong px-4 py-8 text-center">
        <p className="font-medium">No agent has run yet</p>
        <p className="mt-1 text-sm text-muted">Logs from the Analysis Skill and Remediation Subagent stream here live.</p>
      </div>
    );
  }
  const run = runs.find((r) => r.id === selectedId) ?? runs[runs.length - 1];
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Agent runs">
        {[...runs].reverse().map((r) => (
          <button
            key={r.id}
            onClick={() => setSelectedId(r.id)}
            aria-pressed={r.id === run.id}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-sm",
              r.id === run.id ? "border-accent bg-accent/10 text-fg" : "border-line text-muted hover:text-fg",
            )}
          >
            {r.kind === "remediation" ? <Wrench className="size-3.5" aria-hidden /> : <Bot className="size-3.5" aria-hidden />}
            {r.kind} #{r.id}
            {r.status === "running" && <span className="size-1.5 animate-pulse-dot rounded-full bg-accent" aria-label="running" />}
          </button>
        ))}
      </div>

      <dl className="grid grid-cols-2 gap-x-6 gap-y-1.5 rounded-md border border-line bg-panel px-4 py-3 text-sm sm:grid-cols-4 lg:grid-cols-7">
        <div>
          <dt className="text-xs text-faint">Status</dt>
          <dd className="mt-0.5">
            <Badge tone={runTone(run.status)}>{run.status}</Badge>
          </dd>
        </div>
        <div>
          <dt className="text-xs text-faint">Kind</dt>
          <dd className="mt-0.5 whitespace-nowrap">
            {run.kind} {run.attempt > 0 && <span className="text-faint">· attempt {run.attempt}</span>}
          </dd>
        </div>
        <div className="col-span-2">
          <dt className="text-xs text-faint">Model</dt>
          <dd className="mt-0.5 truncate font-mono text-[0.82rem]">{run.model ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-xs text-faint">{run.finished_at ? "Duration" : "Elapsed"}</dt>
          <dd className="mt-0.5 font-mono tabular-nums">{durationBetween(run.started_at, run.finished_at, now)}</dd>
        </div>
        <div>
          <dt className="text-xs text-faint">Turns</dt>
          <dd className="mt-0.5 font-mono tabular-nums">{run.num_turns ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-xs text-faint">Cost</dt>
          <dd className="mt-0.5 font-mono tabular-nums">{formatCost(run.cost_usd)}</dd>
        </div>
      </dl>
      {run.error && <p className="rounded-md border border-bad/40 bg-bad/10 px-3 py-2 text-sm text-bad">{run.error}</p>}

      <LogStream key={run.id} taskId={taskId} run={run} />
    </div>
  );
}
