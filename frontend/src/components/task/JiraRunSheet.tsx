import { useQuery } from "@tanstack/react-query";
import { Bell, ClipboardList, ExternalLink, FileDiff, LayoutDashboard, ListTree, MessageSquareText, ShieldCheck } from "lucide-react";
import { DiffView } from "@/components/common/DiffView";
import { Badge } from "@/components/ui/badge";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { absoluteTime, humanize } from "@/lib/format";
import { api } from "@/services/api";
import { JiraRunAction } from "./JiraRunAction";
import { JiraRunTimeline } from "./JiraRunTimeline";

function JiraRunDetail({ runId }: { runId: string }) {
  const { data, error } = useQuery({
    queryKey: ["jira-workflow", "run", runId],
    queryFn: () => api.jiraRun(runId),
    refetchInterval: 3_000,
  });

  if (!data) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-2 p-10 text-center">
        <SheetTitle className="font-semibold">{error ? "Couldn't load this ticket" : "Loading ticket…"}</SheetTitle>
        {error && <SheetDescription className="text-sm text-muted">{error.message}</SheetDescription>}
      </div>
    );
  }

  const { run, issue, repair, drafts, timeline } = data;
  return (
    <>
      <header className="space-y-3 border-b border-line px-6 pb-4 pt-5 pr-12">
        <p className="font-mono text-xs text-muted">{run.issue_key} · {run.source_kind === "training" ? "Training Jira" : humanize(run.source_kind)}</p>
        <SheetTitle className="text-xl font-semibold">{issue?.title ?? run.title ?? run.issue_key}</SheetTitle>
        <div className="flex flex-wrap gap-1.5">
          <Badge tone="info">{humanize(run.state)}</Badge>
          {issue && <Badge>Jira {humanize(issue.status)}</Badge>}
          {run.repair_status && <Badge tone={run.repair_status === "passed" ? "success" : run.repair_status === "failed" ? "danger" : "neutral"}>
            Repair {humanize(run.repair_status).toLowerCase()}
          </Badge>}
        </div>
        {(run.last_error || repair?.error) && (
          <div role="status" className="rounded-md border border-bad/30 bg-bad/5 p-3 text-sm">
            <p className="break-words font-medium text-bad">{run.last_error || repair?.error}</p>
            {run.state === "needs_intervention" && run.thread_url && (
              <a className="mt-1 inline-block underline" href={run.thread_url} target="_blank" rel="noreferrer">
                Відкрити тред і відповісти на блокер у Slack
              </a>
            )}
          </div>
        )}
        <JiraRunAction run={run} hasPlan={
          run.state !== "needs_intervention" || run.last_error === repair?.error ? Boolean(repair?.plan) : undefined
        } />
      </header>
      <Tabs defaultValue="overview" className="flex min-h-0 flex-1 flex-col">
        <TabsList className="shrink-0 px-4" aria-label="Ticket details">
          <TabsTrigger value="overview"><LayoutDashboard aria-hidden /> Overview</TabsTrigger>
          <TabsTrigger value="timeline"><ListTree aria-hidden /> Timeline</TabsTrigger>
          <TabsTrigger value="drafts"><MessageSquareText aria-hidden /> Drafts</TabsTrigger>
          <TabsTrigger value="plan"><ClipboardList aria-hidden /> Plan</TabsTrigger>
          <TabsTrigger value="diff"><FileDiff aria-hidden /> Diff</TabsTrigger>
          <TabsTrigger value="validation"><ShieldCheck aria-hidden /> Validation</TabsTrigger>
          <TabsTrigger value="slack"><Bell aria-hidden /> Slack</TabsTrigger>
        </TabsList>
        <div className="min-h-0 flex-1 overflow-y-auto px-6 pb-10 scroll-thin">
          <TabsContent value="overview" className="space-y-4">
            <div className="text-sm text-muted">
              <p>Slack reporter · {data.reporter_slack_id}</p>
              <p className="break-all font-mono text-xs">{run.run_id}</p>
            </div>
            {issue && (
              <section>
                <h3 className="mb-2 font-semibold">Jira description</h3>
                <p className="whitespace-pre-wrap break-words rounded-md border border-line bg-panel p-3 text-sm">{issue.description_text}</p>
              </section>
            )}
          </TabsContent>
          <TabsContent value="timeline">
            <JiraRunTimeline key={runId} timeline={timeline} />
          </TabsContent>
          <TabsContent value="drafts">
            {drafts.length === 0 && <p className="text-sm text-muted">No drafts yet.</p>}
            <ul className="divide-y divide-line">
              {drafts.map((draft) => (
                <li key={draft.version} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                  <span className="font-medium">v{draft.version}</span>
                  <Badge>{humanize(draft.status)}</Badge>
                  {draft.decision && <span>Reporter decision · {humanize(draft.decision)}</span>}
                  {draft.decided_at && <time dateTime={draft.decided_at} className="text-xs text-muted">{absoluteTime(draft.decided_at)}</time>}
                </li>
              ))}
            </ul>
          </TabsContent>
          <TabsContent value="plan" className="space-y-4 text-sm">
            {repair?.plan ? (
              <>
                {repair.plan.route && (
                  <dl className="space-y-1">
                    <div><dt className="inline font-semibold">Route · </dt><dd className="inline">{repair.plan.route.id}</dd></div>
                    <div><dt className="inline font-semibold">Executor · </dt><dd className="inline">{repair.plan.route.execution_agent}</dd></div>
                    <div><dt className="inline font-semibold">QA · </dt><dd className="inline">{repair.plan.route.qa_agent}</dd></div>
                  </dl>
                )}
                <section><h3 className="font-semibold">Goal</h3><p>{repair.plan.goal}</p></section>
                <section>
                  <h3 className="font-semibold">Steps</h3>
                  <ol className="list-decimal space-y-1 pl-5">
                    {repair.plan.steps.map((step, index) => <li key={index}>{step}</li>)}
                  </ol>
                </section>
                <section>
                  <h3 className="font-semibold">Acceptance criteria</h3>
                  <ul className="list-disc space-y-1 pl-5">
                    {repair.plan.acceptance_criteria.map((criterion, index) => <li key={index}>{criterion}</li>)}
                  </ul>
                </section>
              </>
            ) : <p className="text-muted">{repair?.error ?? "No plan yet."}</p>}
          </TabsContent>
          <TabsContent value="diff" className="space-y-3">
            {repair?.summary && <p className="text-sm">{repair.summary}</p>}
            {repair?.patch ? <DiffView diff={repair.patch} /> : <p className="text-sm text-muted">No patch yet.</p>}
          </TabsContent>
          <TabsContent value="validation" className="space-y-3">
            {repair?.qa && (
              <section className="space-y-1 text-sm">
                <h3 className="font-semibold">QA · {humanize(repair.qa.verdict)}</h3>
                <p>{repair.qa.summary}</p>
              </section>
            )}
            {repair?.error && <p className="text-sm text-bad">{repair.error}</p>}
            {repair?.review_script_checked && <p className="text-sm">Reviewer ran the page-check skill script.</p>}
            {repair?.test_output ? (
              <pre className="overflow-x-auto rounded-md border border-line bg-sunken p-3 font-mono text-xs">{repair.test_output}</pre>
            ) : !repair?.error && <p className="text-sm text-muted">No test results yet.</p>}
          </TabsContent>
          <TabsContent value="slack">
            {run.thread_url ? (
              <a href={run.thread_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 text-sm text-accent underline">
                Open Slack thread <ExternalLink className="size-4" aria-hidden />
              </a>
            ) : <p className="text-sm text-muted">Slack thread pending.</p>}
          </TabsContent>
        </div>
      </Tabs>
    </>
  );
}

export function JiraRunSheet({ runId, onClose }: { runId: string | null; onClose: () => void }) {
  return (
    <Sheet open={runId !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent aria-describedby={undefined} onCloseAutoFocus={(event) => {
        const card = document.getElementById(`jira-card-${runId}`);
        if (card) {
          event.preventDefault();
          card.focus();
        }
      }}>
        {runId !== null && <JiraRunDetail key={runId} runId={runId} />}
      </SheetContent>
    </Sheet>
  );
}
