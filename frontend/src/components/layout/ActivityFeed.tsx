import { ChevronRight, PanelRightClose } from "lucide-react";
import { Link } from "react-router-dom";
import { EventIcon } from "@/components/common/EventIcon";
import { levelColor } from "@/lib/events";
import { Button } from "@/components/ui/button";
import { useEvents } from "@/hooks/queries";
import { useNow } from "@/hooks/useNow";
import { clockTime, relativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";

export function ActivityFeed({ onCollapse }: { onCollapse: () => void }) {
  const { data, isLoading, isError, error } = useEvents(60);
  const now = useNow(5000);

  return (
    <aside className="flex h-full min-h-0 flex-col rounded-lg border border-line bg-panel" aria-label="Live activity">
      <div className="flex items-center justify-between border-b border-line px-3 py-2">
        <h2 className="text-sm font-semibold">Activity</h2>
        <Button variant="ghost" size="icon" onClick={onCollapse} aria-label="Hide activity feed">
          <PanelRightClose />
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto scroll-thin">
        {isLoading && <p className="px-3 py-4 text-sm text-muted">Loading recent events…</p>}
        {isError && <p className="px-3 py-4 text-sm text-bad">Couldn't load events: {(error as Error).message}</p>}
        {data && data.length === 0 && (
          <p className="px-3 py-4 text-sm text-muted">Nothing has happened yet. Events appear here the moment the worker records them.</p>
        )}
        <ol className="flex flex-col">
          {data?.map((e) => {
            const body = (
              <div className="flex gap-2.5 px-3 py-2.5">
                <EventIcon type={e.type} level={e.level} className="mt-0.5" />
                <div className="min-w-0 flex-1">
                  <p className={cn("text-[0.82rem] leading-snug", e.level === "info" ? "text-fg/90" : levelColor(e.level))}>{e.message}</p>
                  <p className="mt-0.5 flex min-w-0 items-center gap-1.5 whitespace-nowrap text-[0.7rem] text-faint">
                    <time dateTime={e.ts} title={clockTime(e.ts)}>{relativeTime(e.ts, now)}</time>
                    {e.task_id !== null && <span className="font-mono">task #{e.task_id}</span>}
                    <span className="truncate font-mono">{e.type}</span>
                  </p>
                </div>
                {e.task_id !== null && <ChevronRight className="mt-1 size-3.5 shrink-0 text-faint" aria-hidden />}
              </div>
            );
            return (
              <li key={e.id} className="animate-card-in border-b border-line/60 last:border-b-0">
                {e.task_id !== null ? (
                  <Link to={`/tasks/${e.task_id}`} className="block hover:bg-raised focus-visible:bg-raised">
                    {body}
                  </Link>
                ) : (
                  body
                )}
              </li>
            );
          })}
        </ol>
      </div>
    </aside>
  );
}
