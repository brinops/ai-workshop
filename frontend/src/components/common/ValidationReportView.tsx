import { AlertOctagon, CheckCircle2, CircleSlash, FileWarning, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { ValidationReport, ValidatorFinding } from "@/services/api";
import { ClassificationChip } from "./StatusBits";

const STAGE_ORDER = ["yaml-parse", "helm-lint", "helm-template", "kubeconform", "consistency"];

function StageStatus({ status }: { status: string }) {
  const map: Record<string, { Icon: typeof CheckCircle2; cls: string }> = {
    passed: { Icon: CheckCircle2, cls: "text-ok" },
    failed: { Icon: XCircle, cls: "text-bad" },
    error: { Icon: AlertOctagon, cls: "text-warn" },
    skipped: { Icon: CircleSlash, cls: "text-faint" },
  };
  const { Icon, cls } = map[status] ?? { Icon: CircleSlash, cls: "text-faint" };
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-xs font-medium", cls)}>
      <Icon className="size-4" aria-hidden />
      {status}
    </span>
  );
}

export function FindingsList({ findings, className }: { findings: ValidatorFinding[]; className?: string }) {
  if (findings.length === 0) return <p className="text-sm text-muted">No findings.</p>;
  return (
    <ul className={cn("flex flex-col divide-y divide-line rounded-md border border-line", className)}>
      {findings.map((f, i) => (
        <li key={i} className="flex flex-col gap-1 px-3 py-2 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <ClassificationChip value={f.category === "TOOL_ERROR" ? "UNKNOWN" : f.category} />
            <Badge tone="neutral" className="font-mono">{f.check}</Badge>
            {f.file && (
              <span className="inline-flex items-center gap-1 font-mono text-xs text-muted">
                <FileWarning className="size-3.5" aria-hidden />
                {f.file}
                {f.line ? `:${f.line}` : ""}
              </span>
            )}
            {f.resource && <span className="font-mono text-xs text-faint">{f.resource}</span>}
          </div>
          <p className="text-fg/90">{f.message}</p>
        </li>
      ))}
    </ul>
  );
}

/** Renders a chart_validator JSON report: per-chart stage table + findings. */
export function ValidationReportView({ report }: { report: ValidationReport | null }) {
  if (!report) return <p className="text-sm text-muted">No report was stored for this run.</p>;
  const charts = report.charts ?? [];
  return (
    <div className="flex flex-col gap-4">
      {report.tool_error && (
        <p className="flex items-start gap-2 rounded-md border border-warn/40 bg-warn/10 px-3 py-2 text-sm text-warn">
          <AlertOctagon className="mt-0.5 size-4 shrink-0" aria-hidden />
          Validator tool error: {report.tool_error}
        </p>
      )}
      {charts.length === 0 && !report.tool_error && <p className="text-sm text-muted">The report lists no charts.</p>}
      {charts.map((c) => {
        const rank = (name: string) => {
          const i = STAGE_ORDER.indexOf(name);
          return i === -1 ? STAGE_ORDER.length : i;
        };
        const stages = [...c.stages].sort((a, b) => rank(a.name) - rank(b.name));
        return (
          <div key={c.chart} className="flex flex-col gap-2">
            <h4 className="font-mono text-sm text-fg">{c.chart}</h4>
            <table className="w-full table-fixed overflow-hidden rounded-md border border-line text-sm">
              <thead className="bg-raised text-left text-xs text-muted">
                <tr>
                  <th className="w-[34%] px-3 py-1.5 font-medium">Stage</th>
                  <th className="w-[22%] px-3 py-1.5 font-medium">Result</th>
                  <th className="px-3 py-1.5 font-medium">Detail</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {stages.map((s) => (
                  <tr key={s.name}>
                    <td className="px-3 py-1.5 font-mono text-xs">{s.name}</td>
                    <td className="px-3 py-1.5">
                      <StageStatus status={s.status} />
                    </td>
                    <td className="px-3 py-1.5 text-xs text-muted">{s.detail || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {c.findings.length > 0 && <FindingsList findings={c.findings} />}
          </div>
        );
      })}
    </div>
  );
}
