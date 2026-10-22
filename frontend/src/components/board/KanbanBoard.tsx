import { Inbox } from "lucide-react";
import { COLUMNS } from "@/lib/states";
import { cn } from "@/lib/utils";
import { useNow } from "@/hooks/useNow";
import type { Board } from "@/services/api";
import { TaskCardView } from "./TaskCardView";

const COLUMN_ACCENT: Record<string, string> = {
  NEW: "bg-gray",
  TODO: "bg-accent",
  IN_PROGRESS: "bg-amber",
  DONE: "bg-ok",
};

export function KanbanBoard({ board, selectedId }: { board: Board; selectedId: number | null }) {
  const now = useNow(5000);
  return (
    <div className="flex min-h-0 flex-1 gap-3 overflow-x-auto pb-2 scroll-thin" role="list" aria-label="Kanban board">
      {COLUMNS.map((col) => {
        const tasks = board.columns[col.id] ?? [];
        return (
          <section
            key={col.id}
            role="listitem"
            aria-label={`${col.title} column, ${tasks.length} tasks`}
            className="flex min-h-0 w-[19rem] min-w-[17rem] flex-1 flex-col rounded-lg border border-line bg-sunken/60"
          >
            <header className="border-b border-line px-3 py-2">
              <div className="flex items-center gap-2">
                <span className={cn("size-2 shrink-0 rounded-full", COLUMN_ACCENT[col.id])} aria-hidden />
                <h2 className="whitespace-nowrap text-sm font-semibold">{col.title}</h2>
                <span className="rounded bg-raised px-1.5 font-mono text-xs tabular-nums text-muted">{board.counts[col.id] ?? tasks.length}</span>
              </div>
              <p className="mt-0.5 truncate text-[0.7rem] text-faint" title={col.hint}>
                {col.hint}
              </p>
            </header>
            <div className="flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto p-2.5 scroll-thin">
              {tasks.length === 0 ? (
                <div className="flex flex-1 flex-col items-center justify-center gap-1.5 py-8 text-center text-xs text-faint">
                  <Inbox className="size-5" aria-hidden />
                  Empty
                </div>
              ) : (
                tasks.map((t) => <TaskCardView key={t.id} task={t} now={now} selected={t.id === selectedId} />)
              )}
            </div>
          </section>
        );
      })}
    </div>
  );
}
