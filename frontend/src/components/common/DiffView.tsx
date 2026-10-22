import { FileDiff, FileMinus2, FilePlus2 } from "lucide-react";
import { useMemo } from "react";
import { cn } from "@/lib/utils";
import { parseUnifiedDiff, type DiffFile } from "@/lib/diff";

function FileHeader({ file }: { file: DiffFile }) {
  const Icon = file.status === "added" ? FilePlus2 : file.status === "deleted" ? FileMinus2 : FileDiff;
  return (
    <div className="flex items-center gap-2 border-b border-line bg-raised px-3 py-2 text-sm">
      <Icon className="size-4 shrink-0 text-muted" aria-hidden />
      <span className="min-w-0 truncate font-mono text-[0.85rem]">
        {file.status === "renamed" && file.oldPath ? `${file.oldPath} → ` : ""}
        {file.path}
      </span>
      {file.status !== "modified" && <span className="text-xs text-faint">{file.status}</span>}
      <span className="ml-auto flex shrink-0 items-center gap-2 font-mono text-xs">
        <span className="text-ok" aria-label={`${file.additions} additions`}>+{file.additions}</span>
        <span className="text-bad" aria-label={`${file.deletions} deletions`}>−{file.deletions}</span>
      </span>
    </div>
  );
}

/** Unified diff with old/new line numbers, +/- coloring and per-file headers. */
export function DiffView({ diff, className, maxHeight }: { diff: string; className?: string; maxHeight?: string }) {
  const files = useMemo(() => parseUnifiedDiff(diff), [diff]);

  if (files.length === 0) {
    if (!diff.trim()) return <p className="text-sm text-muted">The diff is empty.</p>;
    return (
      <pre className="overflow-x-auto rounded-md border border-line bg-sunken p-3 font-mono text-xs scroll-thin">{diff}</pre>
    );
  }

  return (
    <div className={cn("flex flex-col gap-3", className)}>
      {files.map((file, fi) => (
        <section key={`${file.path}-${fi}`} className="overflow-hidden rounded-md border border-line bg-sunken" aria-label={`Changes in ${file.path}`}>
          <FileHeader file={file} />
          <div className="overflow-auto scroll-thin" style={maxHeight ? { maxHeight } : undefined}>
            <table className="diff-table w-full border-collapse font-mono text-[0.8rem] leading-[1.55]">
              <tbody>
                {file.hunks.map((hunk, hi) => (
                  <HunkRows key={hi} header={hunk.header} lines={hunk.lines} />
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}
    </div>
  );
}

function HunkRows({ header, lines }: { header: string; lines: DiffFile["hunks"][number]["lines"] }) {
  return (
    <>
      <tr>
        <td colSpan={4} className="bg-accent/[0.06] px-3 py-1 text-xs text-accent/80">
          {header}
        </td>
      </tr>
      {lines.map((l, i) => {
        const sign = l.type === "add" ? "+" : l.type === "del" ? "−" : l.type === "meta" ? "" : " ";
        return (
          <tr
            key={i}
            className={cn(
              l.type === "add" && "bg-[var(--diff-add-bg)] text-[var(--diff-add-fg)]",
              l.type === "del" && "bg-[var(--diff-del-bg)] text-[var(--diff-del-fg)]",
              l.type === "meta" && "text-faint italic",
            )}
          >
            <td className="w-[1%] select-none border-r border-line/60 whitespace-nowrap px-2 text-right text-faint/80 tabular-nums">{l.oldNo ?? ""}</td>
            <td className="w-[1%] select-none border-r border-line/60 whitespace-nowrap px-2 text-right text-faint/80 tabular-nums">{l.newNo ?? ""}</td>
            <td className="w-[1%] select-none pl-2 pr-1 text-center" aria-hidden>
              {sign}
            </td>
            <td className="whitespace-pre pr-4">
              <span className="sr-only">{l.type === "add" ? "added: " : l.type === "del" ? "removed: " : ""}</span>
              {l.text || " "}
            </td>
          </tr>
        );
      })}
    </>
  );
}
