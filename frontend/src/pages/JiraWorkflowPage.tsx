import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as Dialog from "@radix-ui/react-dialog";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { BoardColumn } from "@/components/board/BoardColumn";
import { JiraRunAction } from "@/components/task/JiraRunAction";
import { JiraRunSheet } from "@/components/task/JiraRunSheet";
import { TopBar } from "@/components/layout/TopBar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { usePresentationMode, useTheme } from "@/hooks/usePreferences";
import { humanize } from "@/lib/format";
import { cn } from "@/lib/utils";
import { api, type JiraRun } from "@/services/api";

const REFRESH_MS = 3_000;
const runsKey = ["jira-workflow", "runs"] as const;

function CreateTrainingIssue({ reporterId }: { reporterId: string }) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const client = useQueryClient();
  const template = useQuery({
    queryKey: ["jira-workflow", "training-issue-template"],
    queryFn: api.trainingIssueTemplate,
    enabled: open,
  });
  const create = useMutation({
    mutationFn: () => api.createTrainingIssue(reporterId, { title: title.trim(), description_text: description.trim() }),
    onSuccess: () => {
      setOpen(false);
      void client.invalidateQueries({ queryKey: runsKey });
    },
  });
  const fieldClass = "w-full rounded-md border border-line bg-bg px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent";

  return (
    <>
      <Dialog.Root open={open} onOpenChange={(next) => {
        if (!create.isPending) setOpen(next);
      }}>
        <Dialog.Trigger asChild>
          <Button onClick={() => create.reset()}>Create training issue</Button>
        </Dialog.Trigger>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-[60] bg-black/60" />
          <Dialog.Content className="fixed left-1/2 top-1/2 z-[61] max-h-[90dvh] w-[min(560px,94vw)] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-lg border border-line-strong bg-panel p-5 shadow-2xl">
            <Dialog.Title className="text-base font-semibold">Create training issue</Dialog.Title>
            <Dialog.Description className="mt-1 text-sm text-muted">
              Use a booking report to try different descriptions and compare the agent’s questions in Slack.
            </Dialog.Description>
            <form className="mt-4 space-y-4" onSubmit={(event) => {
              event.preventDefault();
              if (!create.isPending && title.trim() && description.trim()) create.mutate();
            }}>
              <div className="space-y-1">
                <label htmlFor="training-issue-title" className="text-sm font-medium">Title</label>
                <input id="training-issue-title" className={fieldClass} value={title} required maxLength={160}
                  onChange={(event) => setTitle(event.target.value)} />
              </div>
              <div className="space-y-1">
                <label htmlFor="training-issue-description" className="text-sm font-medium">Description</label>
                <textarea id="training-issue-description" className={fieldClass} value={description} required rows={5} maxLength={3000}
                  onChange={(event) => setDescription(event.target.value)} />
              </div>
              {create.error && <p role="alert" className="text-sm text-bad">{create.error.message}</p>}
              <div className="flex flex-wrap items-center gap-2">
                <Button type="button" variant="ghost" disabled={!template.data || create.isPending} onClick={() => {
                  if (template.data) {
                    setTitle(template.data.title);
                    setDescription(template.data.description_text);
                  }
                }}>Use booking example</Button>
                <div className="ml-auto flex gap-2">
                  <Dialog.Close asChild><Button type="button" variant="ghost" disabled={create.isPending}>Cancel</Button></Dialog.Close>
                  <Button type="submit" variant="primary" disabled={create.isPending || !title.trim() || !description.trim()}>
                    {create.isPending ? "Creating…" : "Create issue"}
                  </Button>
                </div>
              </div>
            </form>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
      {create.data && (
        <p role="status" className="text-sm text-muted">Created {create.data.issue_key}. Its run appears here after the scheduler picks it up.</p>
      )}
    </>
  );
}

function WorkshopSetup() {
  const pairing = useQuery({
    queryKey: ["jira-workflow", "pairing"], queryFn: api.slackPairing,
    refetchInterval: (query) => query.state.data?.state === "pending" ? REFRESH_MS : false,
  });
  const start = useMutation({
    mutationFn: api.startSlackPairing,
    onSuccess: () => void pairing.refetch(),
  });
  const reporterId = pairing.data?.reporter_id;
  const pairingState = pairing.data?.state;
  const code = start.data?.code;
  const error = start.error ?? pairing.error;

  return (
    <section aria-labelledby="workshop-setup" className="flex shrink-0 flex-wrap items-center gap-3 rounded-lg border border-line bg-panel px-3 py-2">
      <h2 id="workshop-setup" className="text-sm font-medium">Workshop setup</h2>
      {pairing.isPending && <p className="text-sm text-muted">Checking Slack connection…</p>}
      {reporterId ? (
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-sm text-ok">Slack connected · {pairing.data?.slack_user_id}</p>
          <CreateTrainingIssue reporterId={reporterId} />
        </div>
      ) : pairing.data && (
        <div className="space-y-2">
          {pairingState === "pending" && code && (
            <p className="text-sm">Send <code className="rounded bg-bg px-1.5 py-0.5">pair {code}</code> in a direct message to the workshop bot.</p>
          )}
          {pairingState === "expired" && <p className="text-sm text-muted">The code expired. Generate a new one to connect.</p>}
          <Button onClick={() => start.mutate()} disabled={start.isPending}>Generate Slack pairing code</Button>
        </div>
      )}
      {error && <p role="alert" className="text-sm text-bad">{error.message}</p>}
    </section>
  );
}

const columns = [
  { id: "discovered", title: "New", hint: "Discovered by the scheduler", accent: "bg-gray" },
  { id: "clarification", title: "Clarification", hint: "Slack discussion and draft approval", accent: "bg-accent" },
  { id: "ready_for_handoff", title: "Ready for handoff", hint: "Approved and recorded in Jira", accent: "bg-violet" },
  { id: "in_progress", title: "In progress", hint: "Agent repair and human review", accent: "bg-amber" },
  { id: "done", title: "Done", hint: "Repair accepted by the operator", accent: "bg-ok" },
];

function columnFor(run: JiraRun) {
  return columns.some((column) => column.id === run.state) ? run.state : "clarification";
}

function JiraKanban({ runs, selectedId }: { runs: JiraRun[]; selectedId: string | null }) {
  return (
    <div className="flex min-h-0 flex-1 gap-3 overflow-x-auto pb-2 scroll-thin" role="list" aria-label="Jira Kanban">
      {columns.map((column) => {
        const cards = runs.filter((run) => columnFor(run) === column.id);
        return (
          <BoardColumn key={column.id} {...column} count={cards.length}>
            {cards.map((run) => {
              const selected = run.run_id === selectedId;
              const status = run.repair_status;
              const busy = status === "pending" || status === "running";
              const passed = status === "passed";
              return (
                <article key={run.run_id} className={cn(
                  "group relative animate-card-in rounded-lg border bg-panel p-3 transition-[border-color,background-color] duration-300",
                  "hover:border-line-strong hover:bg-raised/60 focus-within:border-accent/60",
                  selected ? "border-accent ring-1 ring-accent/40" : busy ? "border-accent/40" : "border-line",
                )}>
                  <div className="flex items-start justify-between gap-2">
                    <span className="font-mono text-[0.72rem] text-muted">{run.issue_key}</span>
                    <Badge tone={run.last_error ? "danger" : run.state === "done" ? "success" : "neutral"}>{humanize(run.state)}</Badge>
                  </div>
                  <h3 className="mt-1 line-clamp-2 text-[0.92rem] font-medium leading-snug">
                    <Link id={`jira-card-${run.run_id}`} to={`?run=${encodeURIComponent(run.run_id)}`}
                      className="after:absolute after:inset-0 after:rounded-lg focus-visible:outline-none">
                      {run.title ?? run.issue_key}
                    </Link>
                  </h3>
                  <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                    <Badge>{run.source_kind === "training" ? "Training Jira" : humanize(run.source_kind)}</Badge>
                    {status && <Badge tone={passed ? "success" : status === "failed" ? "danger" : "info"}>Repair {humanize(status).toLowerCase()}</Badge>}
                  </div>
                  {run.last_error && <p className="mt-2 break-words text-xs text-bad">{run.last_error}</p>}
                  <JiraRunAction run={run} className="relative z-10 mt-2.5" />
                </article>
              );
            })}
          </BoardColumn>
        );
      })}
    </div>
  );
}

export function JiraWorkflowPage() {
  const { light, toggleTheme } = useTheme();
  const { togglePresenting } = usePresentationMode();
  const [params, setParams] = useSearchParams();
  const selectedId = params.get("run") || null;
  const runs = useQuery({ queryKey: runsKey, queryFn: api.jiraRuns, refetchInterval: REFRESH_MS });

  return (
    <div className="flex h-screen min-h-0 flex-col">
      <TopBar presenting={false} onTogglePresenting={togglePresenting} light={light} onToggleTheme={toggleTheme} />
      <main className="flex min-h-0 flex-1 flex-col gap-4 px-5 py-4">
        <h1 className="sr-only">Jira Workflow</h1>
        <WorkshopSetup />
        {runs.isPending && <p className="flex flex-1 items-center justify-center text-muted">Loading the board…</p>}
        {runs.isError && <p role="alert" className="text-sm text-bad">{runs.error.message}</p>}
        {runs.data && <JiraKanban runs={runs.data} selectedId={selectedId} />}
      </main>
      <JiraRunSheet runId={selectedId} onClose={() => setParams({}, { replace: true })} />
    </div>
  );
}
