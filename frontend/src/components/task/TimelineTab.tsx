import { EventIcon } from "@/components/common/EventIcon";
import { levelColor } from "@/lib/events";
import { useNow } from "@/hooks/useNow";
import { absoluteTime, relativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { EventOut } from "@/services/api";

export function Timeline({ events, limit, compact = false }: { events: EventOut[]; limit?: number; compact?: boolean }) {
  const now = useNow(5000);
  const ordered = [...events].reverse();
  const shown = limit ? ordered.slice(0, limit) : ordered;
  if (shown.length === 0) return <p className="text-sm text-muted">No events recorded yet.</p>;
  return (
    <ol className="relative flex flex-col" aria-label="Task timeline, newest first">
      {shown.map((e, i) => (
        <li key={e.id} className={cn("relative flex gap-3", compact ? "pb-3" : "pb-4", i === 0 && "animate-card-in")}>
          {i < shown.length - 1 && <span className="absolute left-3 top-7 bottom-0 w-px bg-line" aria-hidden />}
          <EventIcon type={e.type} level={e.level} />
          <div className="min-w-0 flex-1 pt-0.5">
            <p className={cn("leading-snug", compact ? "text-sm" : "text-[0.9rem]", e.level === "info" ? "text-fg/95" : levelColor(e.level))}>
              {e.message}
            </p>
            <p className="mt-0.5 flex flex-wrap gap-x-2 text-xs text-faint">
              <time dateTime={e.ts}>{absoluteTime(e.ts)}</time>
              <span>{relativeTime(e.ts, now)}</span>
              {!compact && <span className="font-mono">{e.type}</span>}
            </p>
          </div>
        </li>
      ))}
    </ol>
  );
}
