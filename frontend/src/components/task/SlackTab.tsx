import { BellOff, CheckCircle2, Clock, MinusCircle, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { absoluteTime, humanize } from "@/lib/format";
import type { NotificationOut } from "@/services/api";

const STATUS = {
  sent: { tone: "success", Icon: CheckCircle2 },
  failed: { tone: "danger", Icon: XCircle },
  skipped: { tone: "gray", Icon: MinusCircle },
  queued: { tone: "amber", Icon: Clock },
} as const;

export function SlackTab({ notifications }: { notifications: NotificationOut[] }) {
  if (notifications.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 rounded-md border border-dashed border-line-strong px-4 py-8 text-center">
        <BellOff className="size-5 text-faint" aria-hidden />
        <p className="font-medium">No notifications yet</p>
        <p className="text-sm text-muted">Slack is notified when a fix lands, or when a human needs to step in.</p>
      </div>
    );
  }
  return (
    <ul className="flex flex-col gap-3">
      {[...notifications].reverse().map((n) => {
        const s = STATUS[n.status as keyof typeof STATUS] ?? STATUS.queued;
        return (
          <li key={n.id} className="rounded-lg border border-line bg-panel p-4">
            <div className="flex flex-wrap items-center gap-2">
              <s.Icon className="size-4" aria-hidden />
              <Badge tone={s.tone}>{n.status}</Badge>
              <span className="text-sm font-medium">{humanize(n.kind)}</span>
              <span className="text-sm text-faint">via {n.channel}</span>
              <time className="ml-auto text-xs text-faint" dateTime={n.ts}>
                {absoluteTime(n.ts)}
              </time>
            </div>
            {n.preview && <p className="mt-2 whitespace-pre-wrap rounded-md bg-sunken px-3 py-2 text-sm text-fg/90">{n.preview}</p>}
            {n.error && <p className="mt-2 text-sm text-bad">{n.error}</p>}
          </li>
        );
      })}
    </ul>
  );
}
