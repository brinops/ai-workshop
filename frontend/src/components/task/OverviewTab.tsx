import { AlertTriangle, FileCode2, Route as RouteIcon, Scale, Search } from "lucide-react";
import type { ReactNode } from "react";
import { ClassificationChip } from "@/components/common/StatusBits";
import { FindingsList } from "@/components/common/ValidationReportView";
import { Badge } from "@/components/ui/badge";
import { useConfig } from "@/hooks/queries";
import { formatPercent } from "@/lib/format";
import { isOverridden, latestDiagnosis } from "@/lib/selectors";
import type { TaskDetail } from "@/services/api";
import { StatusCallout } from "./StatusCallout";

function Section({ title, children, icon: Icon }: { title: string; children: ReactNode; icon?: typeof Search }) {
  return (
    <section className="flex flex-col gap-2">
      <h3 className="flex items-center gap-1.5 text-sm font-semibold text-fg">
        {Icon && <Icon className="size-4 text-muted" aria-hidden />}
        {title}
      </h3>
      {children}
    </section>
  );
}

function RouteSection({ repo, check }: { repo: string; check: string }) {
  const { data } = useConfig();
  const route = data?.repositories.find((r) => r.repo.toLowerCase() === repo.toLowerCase())?.routes.find((r) => r.check === check);
  return (
    <Section title="Route (control-plane.yaml)" icon={RouteIcon}>
      {!route ? (
        <p className="text-sm text-muted">
          Route <span className="font-mono">{check}</span> is not in the active configuration.
        </p>
      ) : (
        <dl className="grid gap-x-6 gap-y-1.5 rounded-md border border-line bg-panel px-4 py-3 text-sm sm:grid-cols-[max-content_1fr]">
          <dt className="text-xs text-faint">Failed check</dt>
          <dd className="font-mono">{route.check}</dd>
          <dt className="text-xs text-faint">Analysis skill</dt>
          <dd className="font-mono">.claude/skills/{route.analysis_skill}</dd>
          <dt className="text-xs text-faint">Remediation agent</dt>
          <dd className="font-mono">.claude/agents/{route.remediation_agent}.md</dd>
          <dt className="text-xs text-faint">Validator</dt>
          <dd className="break-all font-mono">{route.validator}</dd>
          <dt className="text-xs text-faint">Allowed paths</dt>
          <dd className="font-mono">{route.allowed_paths.join(", ")}</dd>
          <dt className="text-xs text-faint">Limits</dt>
          <dd>
            ≤ {route.max_changed_lines} changed lines · {route.max_attempts} attempts
          </dd>
        </dl>
      )}
    </Section>
  );
}

export function OverviewTab({ detail }: { detail: TaskDetail }) {
  const { task } = detail;
  const diag = latestDiagnosis(detail);
  const analysis = diag?.data.analysis;
  const rec = diag?.data.reconciled;
  const fix = analysis?.proposed_fix;
  const overridden = isOverridden(diag?.data);

  return (
    <div className="flex flex-col gap-6">
      <StatusCallout task={task} />
      {task.route && <RouteSection repo={task.repo} check={task.route} />}

      {!diag ? (
        <div className="rounded-md border border-dashed border-line-strong px-4 py-6 text-center">
          <p className="font-medium">No diagnosis yet</p>
          <p className="mt-1 text-sm text-muted">
            {task.state === "ANALYZING"
              ? "The Analysis Skill is diagnosing the failure — results appear here when it finishes."
              : task.state === "WAITING_CI" && task.ci_status === "failure"
                ? "CI has failed. Analysis starts automatically, or when you choose “Analyze now”."
                : task.ci_status === "failure"
                  ? "No diagnosis was recorded for this task."
                  : "Analysis runs only when the required CI check fails."}
          </p>
        </div>
      ) : (
        <>
          <Section title="Root cause" icon={Search}>
            <p className="max-w-[75ch] leading-relaxed text-fg/95">{analysis?.root_cause ?? task.root_cause ?? "—"}</p>
          </Section>

          <Section title="Classification" icon={Scale}>
            <div className="grid gap-2 sm:grid-cols-3">
              <div className="rounded-md border border-line bg-panel p-3">
                <p className="text-xs text-faint">Final</p>
                <div className="mt-1.5 flex flex-wrap items-center gap-2">
                  <ClassificationChip value={rec?.classification ?? task.classification} />
                  {overridden && (
                    <Badge tone="warning">
                      <AlertTriangle aria-hidden /> overridden
                    </Badge>
                  )}
                </div>
                <p className="mt-1.5 text-xs text-muted">Confidence {formatPercent(analysis?.confidence ?? task.confidence)}</p>
              </div>
              <div className="rounded-md border border-line bg-panel p-3">
                <p className="text-xs text-faint">LLM (Analysis Skill)</p>
                <div className="mt-1.5">
                  {rec?.llm_classification ? <ClassificationChip value={rec.llm_classification} /> : <span className="text-sm text-faint">—</span>}
                </div>
              </div>
              <div className="rounded-md border border-line bg-panel p-3">
                <p className="text-xs text-faint">Deterministic (validator)</p>
                <div className="mt-1.5">
                  {rec?.deterministic_classification ? (
                    <ClassificationChip value={rec.deterministic_classification} />
                  ) : (
                    <span className="text-sm text-faint">No validator evidence</span>
                  )}
                </div>
              </div>
            </div>
            {rec && (
              <p className="text-sm text-muted">
                <span className={rec.remediable ? "text-ok" : "text-warn"}>{rec.remediable ? "Auto-remediable." : "Not auto-remediable."}</span>{" "}
                {rec.decision_reason}
              </p>
            )}
            {analysis?.auto_remediation_rationale && (
              <p className="text-sm text-muted">
                <span className="text-faint">Agent's view:</span> {analysis.auto_remediation_rationale}
              </p>
            )}
            {rec?.out_of_scope_files && rec.out_of_scope_files.length > 0 && (
              <p className="text-sm text-warn">Outside the allowed paths: {rec.out_of_scope_files.join(", ")}</p>
            )}
          </Section>

          {fix && (fix.summary || fix.steps?.length || fix.changes?.length) ? (
            <Section title="Remediation plan" icon={FileCode2}>
              {fix.summary && <p className="max-w-[75ch] text-fg/95">{fix.summary}</p>}
              {fix.steps && fix.steps.length > 0 && (
                <ol className="ml-5 list-decimal space-y-1 text-sm text-fg/90 marker:text-faint">
                  {fix.steps.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ol>
              )}
              {fix.changes && fix.changes.length > 0 && (
                <ul className="flex flex-col divide-y divide-line rounded-md border border-line">
                  {fix.changes.map((c, i) => (
                    <li key={i} className="flex flex-col gap-0.5 px-3 py-2 text-sm sm:flex-row sm:gap-3">
                      <code className="shrink-0 font-mono text-[0.82rem] text-accent">{c.file}</code>
                      <span className="text-muted">{c.description}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Section>
          ) : null}

          {analysis?.affected_files && analysis.affected_files.length > 0 && (
            <Section title="Affected files">
              <ul className="flex flex-col divide-y divide-line rounded-md border border-line">
                {analysis.affected_files.map((f, i) => (
                  <li key={i} className="flex flex-col gap-0.5 px-3 py-2 text-sm sm:flex-row sm:gap-3">
                    <code className="shrink-0 font-mono text-[0.82rem]">
                      {f.path}
                      {f.line ? <span className="text-faint">:{f.line}</span> : null}
                    </code>
                    {f.reason && <span className="text-muted">{f.reason}</span>}
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {analysis?.evidence && analysis.evidence.length > 0 && (
            <Section title="Evidence">
              <ul className="flex flex-col gap-1.5">
                {analysis.evidence.map((e, i) => (
                  <li key={i} className="flex gap-2 text-sm">
                    <Badge tone="neutral" className="shrink-0 font-mono">{e.source}</Badge>
                    <span className="text-fg/90">{e.detail}</span>
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {diag.data.findings && diag.data.findings.length > 0 && (
            <Section title={`Validator findings (${diag.data.findings_source === "local" ? "local run" : "from CI log"})`}>
              <FindingsList findings={diag.data.findings} />
            </Section>
          )}
        </>
      )}
    </div>
  );
}
