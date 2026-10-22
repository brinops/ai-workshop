import { CheckCircle2, ExternalLink, XCircle } from "lucide-react";
import { Sha, VerdictBadge } from "@/components/common/StatusBits";
import { ValidationReportView } from "@/components/common/ValidationReportView";
import { Badge } from "@/components/ui/badge";
import { absoluteTime, humanize } from "@/lib/format";
import type { CISnapshotOut, ValidationRunOut } from "@/services/api";

function LocalRun({ v }: { v: ValidationRunOut }) {
  return (
    <article className="flex flex-col gap-3 rounded-lg border border-line bg-panel p-4">
      <header className="flex flex-wrap items-center gap-2">
        {v.valid ? <CheckCircle2 className="size-5 text-ok" aria-hidden /> : <XCircle className="size-5 text-bad" aria-hidden />}
        <span className="font-medium">{v.valid ? "Valid" : "Invalid"}</span>
        <Badge tone="neutral">{humanize(v.purpose)}</Badge>
        <span className="text-sm text-faint">on</span> <Sha sha={v.sha} />
        <span className="text-xs text-faint">exit {v.exit_code}</span>
        <time className="ml-auto text-xs text-faint" dateTime={v.ts}>
          {absoluteTime(v.ts)}
        </time>
      </header>
      <ValidationReportView report={v.report} />
    </article>
  );
}

function CISnapshot({ s }: { s: CISnapshotOut }) {
  return (
    <article className="rounded-lg border border-line bg-panel">
      <header className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2">
        <VerdictBadge verdict={s.overall} />
        <span className="text-sm text-faint">commit</span> <Sha sha={s.sha} />
        <time className="ml-auto text-xs text-faint" dateTime={s.ts}>
          {absoluteTime(s.ts)}
        </time>
      </header>
      {s.checks.length === 0 ? (
        <p className="px-4 py-3 text-sm text-muted">GitHub reported no checks for this commit yet.</p>
      ) : (
        <ul className="divide-y divide-line">
          {s.checks.map((c, i) => (
            <li key={`${c.name}-${i}`} className="flex flex-wrap items-center gap-2 px-4 py-2 text-sm">
              <span className="font-mono">{c.name}</span>
              <VerdictBadge verdict={c.verdict} />
              {c.conclusion && c.conclusion !== c.verdict && <span className="text-xs text-faint">({c.conclusion})</span>}
              {c.html_url && (
                <a href={c.html_url} target="_blank" rel="noreferrer" className="ml-auto inline-flex items-center gap-1 text-xs text-accent hover:underline">
                  Open on GitHub <ExternalLink className="size-3" aria-hidden />
                </a>
              )}
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}

export function ValidationTab({ validations, ci }: { validations: ValidationRunOut[]; ci: CISnapshotOut[] }) {
  return (
    <div className="grid gap-6 xl:grid-cols-2">
      <section className="flex flex-col gap-3">
        <h3 className="text-sm font-semibold">Local validation (control plane)</h3>
        {validations.length === 0 ? (
          <p className="rounded-md border border-dashed border-line-strong px-4 py-6 text-center text-sm text-muted">
            The backend validates charts locally before analysis and after every fix. Nothing has run yet.
          </p>
        ) : (
          [...validations].reverse().map((v) => <LocalRun key={v.id} v={v} />)
        )}
      </section>
      <section className="flex flex-col gap-3">
        <h3 className="text-sm font-semibold">GitHub Actions</h3>
        {ci.length === 0 ? (
          <p className="rounded-md border border-dashed border-line-strong px-4 py-6 text-center text-sm text-muted">
            No CI results recorded yet — the worker polls GitHub Actions and records each change here.
          </p>
        ) : (
          [...ci].reverse().map((s) => <CISnapshot key={s.id} s={s} />)
        )}
      </section>
    </div>
  );
}
