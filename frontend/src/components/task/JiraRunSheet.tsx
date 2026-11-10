import { useQuery } from "@tanstack/react-query";
import { Bell, ClipboardList, ExternalLink, FileDiff, LayoutDashboard, ListTree, MessageSquareText, ShieldCheck } from "lucide-react";
import { DiffView } from "@/components/common/DiffView";
import { Badge } from "@/components/ui/badge";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { absoluteTime, humanize } from "@/lib/format";
import { api, type JiraTimelineEntry } from "@/services/api";
import { JiraRunAction } from "./JiraRunAction";

const eventLabels: Record<string, string> = {
  "jira.issue_discovered": "Jira issue discovered",
  "jira.description_appended": "Jira description updated",
  "slack.thread_opened": "Slack thread opened",
  "slack.thread_reply": "Reporter replied in Slack",
  "slack.reply_posted": "Bot replied in Slack",
  "slack.confirmation_posted": "Confirmation posted in Slack",
  "workshop.agent_started": "Agent started",
  "workshop.agent_finished": "Agent finished",
  "workshop.subagent_started": "Subagent started",
  "workshop.subagent_finished": "Subagent finished",
  "workshop.handoff_start": "Booking repair queued",
  "workshop.booking_plan_result": "Booking repair plan",
  "workshop.booking_repair_result": "Booking repair verification",
  "workshop.handoff_finish": "Agent work marked complete",
};

function eventLabel(entry: JiraTimelineEntry) {
  if (entry.event_type === "slack.draft_action") {
    const draft = entry.draft_version === null ? "draft" : `draft v${entry.draft_version}`;
    if (entry.outcome !== "accepted") return `Slack ${humanize(entry.action).toLowerCase()} click for ${draft}`;
    return entry.action === "approve" ? `Reporter approved ${draft}` : `Reporter requested changes to ${draft}`;
  }
  return eventLabels[entry.event_type] ?? entry.event_type;
}

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
        <JiraRunAction run={run} />
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
            {timeline.length === 0 && <p className="text-sm text-muted">No events yet.</p>}
            <ol className="divide-y divide-line">
              {timeline.map((event) => (
                <li key={event.id} className="flex flex-wrap justify-between gap-x-3 gap-y-1 py-2 text-sm">
                  <span>
                    {eventLabel(event)}
                    {event.agent_type && <span className="font-mono"> · {event.agent_type}</span>}
                    {[event.status, event.hook_status !== "recorded" && event.hook_status, event.stage,
                      event.outcome !== "accepted" && event.outcome].filter(Boolean).map((value, index) => (
                      <span key={index} className="text-muted"> · {humanize(value || null)}</span>
                    ))}
                  </span>
                  <time dateTime={event.received_at} className="text-xs text-muted">{absoluteTime(event.received_at)}</time>
                </li>
              ))}
            </ol>
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
            {repair?.error && <p className="text-sm text-bad">{repair.error}</p>}
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
