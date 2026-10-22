import { ExternalLink } from "lucide-react";
import { humanize } from "@/lib/format";

function isUrl(v: unknown): v is string {
  return typeof v === "string" && /^https?:\/\//.test(v);
}

function Value({ value }: { value: unknown }) {
  if (value === null || value === undefined || value === "") return <span className="text-faint">—</span>;
  if (isUrl(value)) {
    return (
      <a href={value} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 break-all text-accent hover:underline">
        {value} <ExternalLink className="size-3 shrink-0" aria-hidden />
      </a>
    );
  }
  if (typeof value === "object") {
    return (
      <pre className="max-h-72 overflow-auto rounded border border-line bg-sunken px-2 py-1.5 font-mono text-[0.75rem] leading-relaxed text-fg/90 scroll-thin">
        {JSON.stringify(value, null, 2)}
      </pre>
    );
  }
  return <span className="break-words font-mono text-[0.8rem] text-fg/90">{String(value)}</span>;
}

/** Key/value view of a JSON object recorded by the backend (event data, run output, …). */
export function DataView({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data).filter(([, v]) => v !== null && v !== undefined);
  if (entries.length === 0) return <p className="text-xs text-faint">No additional data recorded.</p>;
  return (
    <dl className="grid grid-cols-[minmax(6rem,max-content)_1fr] gap-x-4 gap-y-1.5 text-sm">
      {entries.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="pt-0.5 text-xs text-faint">{humanize(k)}</dt>
          <dd className="min-w-0">
            <Value value={v} />
          </dd>
        </div>
      ))}
    </dl>
  );
}
