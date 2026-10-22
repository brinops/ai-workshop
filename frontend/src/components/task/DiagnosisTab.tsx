import { Bot, Wrench } from "lucide-react";
import { Markdown } from "@/components/common/Markdown";
import { Badge } from "@/components/ui/badge";
import { absoluteTime } from "@/lib/format";
import type { CommentOut, TaskCard } from "@/services/api";

const AUTHOR: Record<string, { label: string; Icon: typeof Bot }> = {
  "analysis-skill": { label: "Analysis Skill", Icon: Bot },
  "remediation-agent": { label: "Remediation Subagent", Icon: Wrench },
};

export function DiagnosisTab({ comments, task }: { comments: CommentOut[]; task: TaskCard }) {
  if (comments.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-line-strong px-4 py-8 text-center">
        <p className="font-medium">No diagnosis yet</p>
        <p className="mt-1 text-sm text-muted">
          {task.state === "ANALYZING"
            ? "The Analysis Skill is working on it — its report lands here."
            : "Analysis runs when the required CI check fails."}
        </p>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      {[...comments].reverse().map((c) => {
        const a = AUTHOR[c.author] ?? { label: c.author, Icon: Bot };
        return (
          <article key={c.id} className="overflow-hidden rounded-lg border border-line bg-panel">
            <header className="flex items-center gap-2 border-b border-line bg-raised/50 px-4 py-2">
              <a.Icon className="size-4 text-accent" aria-hidden />
              <span className="text-sm font-medium">{a.label}</span>
              <Badge tone={c.kind === "diagnosis" ? "info" : c.kind === "remediation" ? "success" : "neutral"}>{c.kind}</Badge>
              <time className="ml-auto text-xs text-faint" dateTime={c.ts}>
                {absoluteTime(c.ts)}
              </time>
            </header>
            <div className="px-4 py-3">
              <Markdown>{c.body_md}</Markdown>
            </div>
          </article>
        );
      })}
    </div>
  );
}
