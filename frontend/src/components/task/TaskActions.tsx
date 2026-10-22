import { Ban, Flag, Pause, Play, RotateCcw, Rocket, Sparkles, Wrench, type LucideIcon } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Tooltip } from "@/components/ui/tooltip";
import { useRunAction } from "@/hooks/useRunAction";
import { ACTION_META, ACTION_ORDER } from "@/lib/actions";
import type { ActionName } from "@/services/api";

const ICON: Record<ActionName, LucideIcon> = {
  analyze: Sparkles,
  start_remediation: Wrench,
  approve_push: Rocket,
  retry: RotateCcw,
  pause: Pause,
  resume: Play,
  cancel: Ban,
  mark_review: Flag,
};

/** Manual controls, rendered strictly from the `actions` list the API returns. */
export function TaskActions({ taskId, actions }: { taskId: number; actions: ActionName[] }) {
  const { run, pending } = useRunAction(taskId);
  const [confirming, setConfirming] = useState<ActionName | null>(null);
  const available = ACTION_ORDER.filter((a) => actions.includes(a));

  if (available.length === 0) {
    return <p className="text-sm text-faint">No manual actions are available in this state.</p>;
  }

  // Exactly one primary call-to-action: the step that moves the pipeline forward.
  const primary = (["approve_push", "start_remediation", "analyze"] as const).find((a) => actions.includes(a));
  const confirmMeta = confirming ? ACTION_META[confirming].confirm : undefined;

  return (
    <div className="flex flex-wrap items-center gap-2" role="toolbar" aria-label="Task actions">
      {available.map((a) => {
        const Icon = ICON[a];
        const meta = ACTION_META[a];
        const prominent = a === primary;
        return (
          <Tooltip key={a} content={meta.description}>
            <Button
              size={a === "approve_push" ? "lg" : "md"}
              variant={a === "cancel" ? "danger" : prominent ? "primary" : "default"}
              disabled={pending !== null}
              onClick={() => (meta.confirm ? setConfirming(a) : run(a))}
              className={a === "cancel" || a === "mark_review" ? "ml-0" : undefined}
            >
              <Icon className={pending === a ? "animate-pulse-dot" : undefined} />
              {meta.label}
            </Button>
          </Tooltip>
        );
      })}
      <ConfirmDialog
        open={confirming !== null}
        onOpenChange={(o) => !o && setConfirming(null)}
        title={confirmMeta?.title ?? ""}
        description={confirmMeta?.body ?? ""}
        confirmLabel={confirmMeta?.confirmLabel ?? "Confirm"}
        destructive
        onConfirm={() => confirming && run(confirming)}
      />
    </div>
  );
}
