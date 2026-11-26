import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, CirclePlay, RotateCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api, type JiraRun } from "@/services/api";

export function JiraRunAction({ run, className, hasPlan }: { run: JiraRun; className?: string; hasPlan?: boolean }) {
  const client = useQueryClient();
  const handoff = useMutation({
    mutationFn: (action: "start" | "finish" | "retry-plan") => api.jiraHandoff(run.run_id, action),
    onSettled: () => void client.invalidateQueries({ queryKey: ["jira-workflow"] }),
  });

  const status = run.repair_status;
  const blocked = run.state === "needs_intervention" && status === "failed" && hasPlan !== undefined;
  if (run.state !== "ready_for_handoff" && run.state !== "in_progress" && !blocked) return null;
  const waitingForPlan = (run.state === "ready_for_handoff" && status !== "planned") || (blocked && !hasPlan);
  const retryPlan = waitingForPlan && status === "failed";
  const busy = (waitingForPlan && !retryPlan) || status === "pending" || status === "running";
  const passed = status === "passed";
  const Icon = passed ? Check : status === "failed" || busy ? RotateCw : CirclePlay;

  return (
    <div className={className}>
      <Button size="sm" variant={passed ? "primary" : "default"} disabled={handoff.isPending || busy}
        onClick={() => handoff.mutate(retryPlan ? "retry-plan" : passed ? "finish" : "start")}>
        <Icon /> {retryPlan ? "Повторити планування" : waitingForPlan ? "Планування…" : passed ? "Завершити" : status === "failed" ? "Повторити" : busy ? "Агент працює…" : "Взяти в роботу"}
      </Button>
      {handoff.isError && <p role="alert" className="mt-1 text-xs text-bad">{handoff.error.message}</p>}
    </div>
  );
}
