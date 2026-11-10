import { COLUMNS } from "@/lib/states";
import { useNow } from "@/hooks/useNow";
import type { Board } from "@/services/api";
import { BoardColumn } from "./BoardColumn";
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
          <BoardColumn key={col.id} title={col.title} hint={col.hint} accent={COLUMN_ACCENT[col.id]} count={board.counts[col.id] ?? tasks.length}>
            {tasks.map((t) => <TaskCardView key={t.id} task={t} now={now} selected={t.id === selectedId} />)}
          </BoardColumn>
        );
      })}
    </div>
  );
}
