import { Braces, ChevronRight, Wrench } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { absoluteTime, humanize } from "@/lib/format";
import type { JiraTimelineEntry } from "@/services/api";

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
  "workshop.handoff_start": "Agent work queued",
  "workshop.booking_plan_result": "Implementation plan",
  "workshop.booking_tests_result": "Automated checks",
  "workshop.booking_qa_result": "QA review",
  "workshop.booking_repair_result": "Implementation result",
  "workshop.blocker": "Workflow blocked",
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

function traceKey(entry: JiraTimelineEntry) {
  return entry.attempt_id && entry.trace?.tool_use_id ? `${entry.attempt_id}:${entry.trace.tool_use_id}` : null;
}

function TraceDetail({ title, trace }: { title: string; trace: NonNullable<JiraTimelineEntry["trace"]> }) {
  return (
    <section>
      <p className={trace.is_error ? "text-xs font-medium text-bad" : "text-xs font-medium text-muted"}>{title}</p>
      <pre className="mt-1 max-h-80 overflow-auto whitespace-pre-wrap break-words rounded border border-line bg-sunken p-3 font-mono text-xs leading-relaxed scroll-thin">
        {trace.detail || "Empty result"}
      </pre>
      {trace.truncated && <p className="mt-1 text-xs text-muted">Output shortened for the timeline.</p>}
    </section>
  );
}

function TraceRow({ entry, result }: { entry: JiraTimelineEntry; result?: JiraTimelineEntry }) {
  const trace = entry.trace;
  if (!trace) return null;
  const structured = trace.kind === "structured_output";
  const call = trace.kind === "tool_use";
  const title = structured ? "Structured output" : trace.tool_name || "Tool result";
  const Icon = structured ? Braces : Wrench;
  return (
    <details className="group py-2 text-sm">
      <summary className="flex cursor-pointer list-none flex-wrap items-center gap-x-2 gap-y-1 rounded px-1 py-1 hover:bg-raised focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent [&::-webkit-details-marker]:hidden">
        <ChevronRight className="size-4 shrink-0 text-muted group-open:rotate-90" aria-hidden />
        <Icon className="size-4 shrink-0 text-accent" aria-hidden />
        <span className="font-mono font-medium">{title}{!call && !structured && trace.tool_name ? " result" : ""}</span>
        {entry.agent_type && <span className="text-xs text-muted">{entry.agent_type}</span>}
        {entry.stage && <span className="text-xs text-muted">{humanize(entry.stage)}</span>}
        {(trace.is_error || result?.trace?.is_error) && <span className="text-xs text-bad">Failed</span>}
        <time dateTime={entry.received_at} className="ml-auto shrink-0 text-xs text-muted">{absoluteTime(entry.received_at)}</time>
      </summary>
      <div className="ml-5 space-y-2 pb-1 pt-2">
        <TraceDetail title={structured ? "JSON output" : call ? "Tool input" : "Tool result"} trace={trace} />
        {result?.trace && <TraceDetail title="Tool result" trace={result.trace} />}
      </div>
    </details>
  );
}

export function JiraRunTimeline({ timeline }: { timeline: JiraTimelineEntry[] }) {
  const [agentOnly, setAgentOnly] = useState(false);
  const calls = new Set<string>();
  const results = new Map<string, JiraTimelineEntry>();
  for (const entry of timeline) {
    const key = traceKey(entry);
    if (!key) continue;
    if (entry.trace?.kind === "tool_use") calls.add(key);
    if (entry.trace?.kind === "tool_result") results.set(key, entry);
  }
  const visible = timeline.filter((entry) => {
    const key = traceKey(entry);
    if (key && entry.trace?.kind === "tool_result" && calls.has(key)) return false;
    return !agentOnly || /^workshop\.(agent_|subagent_|booking_|blocker$)/.test(entry.event_type);
  });

  return (
    <>
      <div className="mb-2 flex gap-1" role="group" aria-label="Timeline filter">
        <Button size="sm" variant={agentOnly ? "ghost" : "default"} aria-pressed={!agentOnly}
          onClick={() => setAgentOnly(false)}>All events</Button>
        <Button size="sm" variant={agentOnly ? "default" : "ghost"} aria-pressed={agentOnly}
          onClick={() => setAgentOnly(true)}>Agent activity</Button>
      </div>
      {agentOnly && !visible.some((entry) => entry.trace) && (
        <p className="mb-2 rounded-md border border-line bg-panel p-3 text-sm text-muted">
          No tool details have been recorded for this run. New agent steps will appear here.
        </p>
      )}
      {!agentOnly && visible.length === 0 && <p className="text-sm text-muted">No events yet.</p>}
      <ol className="divide-y divide-line">
        {visible.map((entry) => {
          const key = traceKey(entry);
          if (entry.trace) {
            return <li key={entry.id}><TraceRow entry={entry} result={key ? results.get(key) : undefined} /></li>;
          }
          return (
            <li key={entry.id} className="flex flex-wrap justify-between gap-x-3 gap-y-1 py-2 text-sm">
              <span>
                {eventLabel(entry)}
                {entry.agent_type && <span className="font-mono"> · {entry.agent_type}</span>}
                {[entry.status, entry.hook_status !== "recorded" && entry.hook_status, entry.stage,
                  entry.outcome !== "accepted" && entry.outcome].filter(Boolean).map((value, index) => (
                  <span key={index} className="text-muted"> · {humanize(value || null)}</span>
                ))}
              </span>
              <time dateTime={entry.received_at} className="text-xs text-muted">{absoluteTime(entry.received_at)}</time>
              {entry.error && <p className="w-full break-words text-xs text-bad">{entry.error}</p>}
            </li>
          );
        })}
      </ol>
    </>
  );
}
