import { Inbox } from "lucide-react";
import { Children, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export function BoardColumn({ title, hint, accent, count, children }: {
  title: string;
  hint: string;
  accent: string;
  count: number;
  children: ReactNode;
}) {
  return (
    <section
      role="listitem"
      aria-label={`${title} column, ${count} tasks`}
      className="flex min-h-0 w-[19rem] min-w-[17rem] flex-1 flex-col rounded-lg border border-line bg-sunken/60"
    >
      <header className="border-b border-line px-3 py-2">
        <div className="flex items-center gap-2">
          <span className={cn("size-2 shrink-0 rounded-full", accent)} aria-hidden />
          <h2 className="whitespace-nowrap text-sm font-semibold">{title}</h2>
          <span className="rounded bg-raised px-1.5 font-mono text-xs tabular-nums text-muted">{count}</span>
        </div>
        <p className="mt-0.5 truncate text-[0.7rem] text-faint" title={hint}>{hint}</p>
      </header>
      <div className="flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto p-2.5 scroll-thin">
        {Children.count(children) === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-1.5 py-8 text-center text-xs text-faint">
            <Inbox className="size-5" aria-hidden />
            Empty
          </div>
        ) : children}
      </div>
    </section>
  );
}
