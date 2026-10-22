import { PanelRightOpen } from "lucide-react";
import { useMemo } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { EmptyBoard } from "@/components/board/EmptyBoard";
import { KanbanBoard } from "@/components/board/KanbanBoard";
import { PipelineStrip } from "@/components/common/Pipeline";
import { ActivityFeed } from "@/components/layout/ActivityFeed";
import { AutomationControls } from "@/components/layout/AutomationControls";
import { TopBar } from "@/components/layout/TopBar";
import { Spotlight } from "@/components/presentation/Spotlight";
import { TaskSheet } from "@/components/task/TaskSheet";
import { Button } from "@/components/ui/button";
import { useBoard } from "@/hooks/queries";
import { usePresentationMode, useStoredFlag, useTheme } from "@/hooks/usePreferences";
import { pickSpotlight } from "@/lib/states";
import type { TaskCard } from "@/services/api";

function parseId(raw: string | undefined): number | null {
  if (!raw) return null;
  const n = Number(raw);
  return Number.isInteger(n) && n > 0 ? n : null;
}

export function DashboardPage() {
  const params = useParams();
  const navigate = useNavigate();
  const selectedId = parseId(params.taskId);
  const { presenting, togglePresenting } = usePresentationMode();
  const { light, toggleTheme } = useTheme();
  const [feedOpen, , toggleFeed] = useStoredFlag("rcp.feed", true);
  const board = useBoard();

  const allTasks = useMemo<TaskCard[]>(
    () => (board.data ? Object.values(board.data.columns).flat() : []),
    [board.data],
  );
  const spotlight = useMemo(() => pickSpotlight(allTasks), [allTasks]);
  const focus = allTasks.find((t) => t.id === selectedId) ?? spotlight;
  const isEmpty = board.data !== undefined && allTasks.length === 0;

  return (
    <div className="flex h-screen min-h-0 flex-col">
      <TopBar presenting={presenting} onTogglePresenting={togglePresenting} light={light} onToggleTheme={toggleTheme} />

      <main className="flex min-h-0 flex-1 flex-col gap-4 px-5 py-4">
        <AutomationControls compact={presenting} />

        {board.isLoading && <div className="flex flex-1 items-center justify-center text-muted">Loading the board…</div>}
        {board.isError && !board.data && (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 text-center">
            <p className="text-lg font-medium">Can't reach the control plane</p>
            <p className="max-w-md text-sm text-muted">
              {(board.error as Error).message}. Start the backend on port 8000 — this page retries automatically.
            </p>
          </div>
        )}

        {isEmpty && <EmptyBoard />}

        {board.data && !isEmpty && presenting && (
          <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto scroll-thin">
            {spotlight && <Spotlight key={spotlight.id} card={focus ?? spotlight} />}
            <div className="flex h-[28rem] shrink-0">
              <KanbanBoard board={board.data} selectedId={focus?.id ?? null} />
            </div>
          </div>
        )}

        {board.data && !isEmpty && !presenting && (
          <>
            {focus && (
              <div className="flex flex-col gap-1.5">
                <p className="text-xs text-muted">
                  Pipeline for{" "}
                  <Link to={`/tasks/${focus.id}`} className="text-fg hover:underline">
                    {focus.repo} #{focus.pr_number}
                  </Link>
                  {focus.id === spotlight?.id && selectedId === null && <span className="text-faint"> (most recent active)</span>}
                </p>
                <PipelineStrip state={focus.state} resolution={focus.resolution} agentRunning={focus.agent_running} />
              </div>
            )}
            <div className="flex min-h-0 flex-1 gap-4">
              <KanbanBoard board={board.data} selectedId={selectedId} />
              {feedOpen ? (
                <div className="hidden w-[22rem] shrink-0 lg:block">
                  <ActivityFeed onCollapse={toggleFeed} />
                </div>
              ) : (
                <Button variant="ghost" size="icon" className="hidden lg:inline-flex" onClick={toggleFeed} aria-label="Show activity feed">
                  <PanelRightOpen />
                </Button>
              )}
            </div>
          </>
        )}
      </main>

      <TaskSheet taskId={selectedId} onClose={() => navigate("/")} />
    </div>
  );
}
