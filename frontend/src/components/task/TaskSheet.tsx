import { Bell, FileDiff, LayoutDashboard, ListTree, MessageSquareText, ShieldCheck, Terminal } from "lucide-react";
import { PipelineStrip } from "@/components/common/Pipeline";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useTask } from "@/hooks/queries";
import { ApiError } from "@/services/api";
import { DiagnosisTab } from "./DiagnosisTab";
import { DiffTab } from "./DiffTab";
import { LogsTab } from "./LogsTab";
import { OverviewTab } from "./OverviewTab";
import { SlackTab } from "./SlackTab";
import { TaskActions } from "./TaskActions";
import { TaskHeader } from "./TaskHeader";
import { Timeline } from "./TimelineTab";
import { ValidationTab } from "./ValidationTab";

function Count({ n }: { n: number }) {
  if (!n) return null;
  return <span className="rounded bg-raised px-1 font-mono text-[0.7rem] tabular-nums text-muted">{n}</span>;
}

function TaskDetailBody({ taskId }: { taskId: number }) {
  const { data, isLoading, isError, error } = useTask(taskId);

  if (isLoading) {
    return (
      <div className="flex flex-1 items-center justify-center p-10 text-muted">
        <SheetTitle className="sr-only">Loading task #{taskId}</SheetTitle>
        <SheetDescription className="sr-only">Loading</SheetDescription>
        Loading task #{taskId}…
      </div>
    );
  }
  if (isError || !data) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-2 p-10 text-center">
        <SheetTitle className="text-lg font-semibold">{notFound ? `Task #${taskId} doesn't exist` : "Couldn't load this task"}</SheetTitle>
        <SheetDescription className="text-sm text-muted">
          {notFound ? "It may have been removed when the database was reset." : (error as Error | null)?.message}
        </SheetDescription>
      </div>
    );
  }

  const { task } = data;
  const runningRun = data.runs.some((r) => r.status === "running");
  return (
    <>
      <div className="flex flex-col gap-4 border-b border-line px-6 pb-4 pt-5">
        <TaskHeader task={task} />
        <PipelineStrip state={task.state} resolution={task.resolution} agentRunning={task.agent_running} />
        <TaskActions taskId={task.id} actions={data.actions} />
      </div>
      <Tabs defaultValue="overview" className="flex min-h-0 flex-1 flex-col">
        <TabsList className="px-4">
          <TabsTrigger value="overview">
            <LayoutDashboard aria-hidden /> Overview
          </TabsTrigger>
          <TabsTrigger value="timeline">
            <ListTree aria-hidden /> Timeline <Count n={data.events.length} />
          </TabsTrigger>
          <TabsTrigger value="diagnosis">
            <MessageSquareText aria-hidden /> Diagnosis <Count n={data.comments.length} />
          </TabsTrigger>
          <TabsTrigger value="diff">
            <FileDiff aria-hidden /> Diff <Count n={data.remediations.length} />
          </TabsTrigger>
          <TabsTrigger value="logs">
            <Terminal aria-hidden /> Agent logs
            {runningRun ? <span className="size-1.5 animate-pulse-dot rounded-full bg-accent" aria-label="live" /> : <Count n={data.runs.length} />}
          </TabsTrigger>
          <TabsTrigger value="validation">
            <ShieldCheck aria-hidden /> Validation <Count n={data.validations.length + data.ci.length} />
          </TabsTrigger>
          <TabsTrigger value="slack">
            <Bell aria-hidden /> Slack <Count n={data.notifications.length} />
          </TabsTrigger>
        </TabsList>
        <div className="min-h-0 flex-1 overflow-y-auto px-6 pb-10 scroll-thin">
          <TabsContent value="overview">
            <OverviewTab detail={data} />
          </TabsContent>
          <TabsContent value="timeline">
            <Timeline events={data.events} />
          </TabsContent>
          <TabsContent value="diagnosis">
            <DiagnosisTab comments={data.comments} task={task} />
          </TabsContent>
          <TabsContent value="diff">
            <DiffTab remediations={data.remediations} task={task} />
          </TabsContent>
          <TabsContent value="logs">
            <LogsTab taskId={task.id} runs={data.runs} />
          </TabsContent>
          <TabsContent value="validation">
            <ValidationTab
              validations={data.validations}
              ci={data.ci}
              trackedSha={task.expected_sha}
              waitingForCi={task.state === "WAITING_CI" || task.state === "VALIDATING"}
            />
          </TabsContent>
          <TabsContent value="slack">
            <SlackTab notifications={data.notifications} />
          </TabsContent>
        </div>
      </Tabs>
    </>
  );
}

export function TaskSheet({ taskId, onClose }: { taskId: number | null; onClose: () => void }) {
  return (
    <Sheet open={taskId !== null} onOpenChange={(o) => !o && onClose()}>
      <SheetContent aria-describedby={undefined}>
        {taskId !== null && <TaskDetailBody key={taskId} taskId={taskId} />}
      </SheetContent>
    </Sheet>
  );
}

