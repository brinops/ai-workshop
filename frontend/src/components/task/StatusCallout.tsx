import { Clock } from "lucide-react";
import { AgentWorking } from "@/components/common/StatusBits";
import { describeTask, type Callout } from "@/lib/describe";
import { cn } from "@/lib/utils";
import type { TaskCard } from "@/services/api";

const TONE: Record<Callout["tone"], string> = {
  info: "border-line-strong bg-raised/60 text-fg",
  warn: "border-warn/40 bg-warn/[0.07] text-warn",
  ok: "border-ok/35 bg-ok/[0.07] text-ok",
  bad: "border-bad/40 bg-bad/[0.07] text-bad",
};

export function StatusCallout({ task, size = "md" }: { task: TaskCard; size?: "md" | "lg" }) {
  if (task.agent_running) return <AgentWorking activity={task.activity} size="lg" />;
  const c = describeTask(task);
  return (
    <div className={cn("flex items-start gap-3 rounded-md border px-3.5 py-2.5", TONE[c.tone])} role="status">
      <c.Icon className={cn("mt-0.5 shrink-0", size === "lg" ? "size-5" : "size-4", c.Icon === Clock && "animate-pulse-dot")} aria-hidden />
      <div className="min-w-0">
        <p className={cn("font-medium", size === "lg" ? "text-base" : "text-sm")}>{c.title}</p>
        {c.body && <p className="mt-0.5 text-sm text-muted">{c.body}</p>}
      </div>
    </div>
  );
}
