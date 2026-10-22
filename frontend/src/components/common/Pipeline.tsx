import { Check } from "lucide-react";
import { Fragment } from "react";
import { cn } from "@/lib/utils";
import { PIPELINE, pipelineStatuses } from "@/lib/states";

/**
 * Detection → Reasoning → Repair → Validation → Visibility.
 * Highlights the stage implied by the task's *current state* (no invented progress).
 */
export function PipelineStrip({
  state,
  resolution,
  agentRunning = false,
  size = "md",
  className,
}: {
  state: string | null;
  resolution?: string | null;
  agentRunning?: boolean;
  size?: "md" | "lg";
  className?: string;
}) {
  const statuses = pipelineStatuses(state, resolution);

  return (
    <ol className={cn("flex w-full items-stretch", className)} aria-label="Remediation pipeline">
      {PIPELINE.map((stage, i) => {
        const st = statuses[stage.id];
        const done = st === "done";
        const active = st === "active";
        const stopped = st === "stopped";
        const nextDone = i < PIPELINE.length - 1 && statuses[PIPELINE[i + 1].id] === "done" && done;
        return (
          <Fragment key={stage.id}>
            <li
              className={cn(
                "relative flex min-w-0 flex-1 flex-col gap-0.5 rounded-md border px-3 transition-colors duration-500",
                size === "lg" ? "py-3" : "py-2",
                active && "border-accent/60 bg-accent/10",
                stopped && "border-warn/50 bg-warn/10",
                done && "border-ok/30 bg-ok/[0.06]",
                st === "idle" && "border-line bg-panel",
              )}
              aria-current={active || stopped ? "step" : undefined}
            >
              <span className="flex items-center gap-1.5">
                <span
                  className={cn(
                    "flex size-5 shrink-0 items-center justify-center rounded-full border font-mono text-[0.65rem]",
                    done && "border-ok/60 bg-ok/20 text-ok",
                    active && "border-accent bg-accent text-accent-fg",
                    stopped && "border-warn bg-warn/20 text-warn",
                    st === "idle" && "border-line-strong text-faint",
                  )}
                  aria-hidden
                >
                  {done ? <Check className="size-3" /> : i + 1}
                </span>
                <span
                  className={cn(
                    "truncate font-medium",
                    size === "lg" ? "text-base" : "text-sm",
                    active || stopped ? "text-fg" : done ? "text-fg/85" : "text-faint",
                  )}
                >
                  {stage.label}
                </span>
                <span className="sr-only">
                  {done ? "(completed)" : active ? "(current)" : stopped ? "(needs attention)" : ""}
                </span>
                {active && agentRunning && (
                  <span className="ml-auto size-2 shrink-0 animate-pulse-dot rounded-full bg-accent" aria-label="agent working" />
                )}
              </span>
              <span className={cn("truncate pl-[1.625rem] text-xs", active || stopped ? "text-muted" : "text-faint")}>
                {stopped ? "Stopped — needs a human" : stage.detail}
              </span>
            </li>
            {i < PIPELINE.length - 1 && (
              <span
                className={cn("mx-1 my-auto h-px w-3 shrink-0 transition-colors", nextDone ? "bg-ok/50" : "bg-line-strong")}
                aria-hidden
              />
            )}
          </Fragment>
        );
      })}
    </ol>
  );
}
