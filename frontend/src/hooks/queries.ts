import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type ActionName, type Automation, type TaskDetail } from "@/services/api";

/* The SSE stream drives most refetches; the intervals are a safety net if it drops. */

export function useBoard() {
  return useQuery({ queryKey: ["board"], queryFn: api.board, refetchInterval: 20_000 });
}

export function useTask(id: number | null) {
  return useQuery({
    queryKey: ["task", id],
    queryFn: () => api.task(id as number),
    enabled: id !== null,
    refetchInterval: 20_000,
  });
}

export function useEvents(limit = 50) {
  return useQuery({ queryKey: ["events", limit], queryFn: () => api.events(limit), refetchInterval: 30_000 });
}

export function useHealth() {
  return useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: 10_000 });
}

export function useAutomation() {
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ["automation"], queryFn: api.automation });
  const mutation = useMutation({
    mutationFn: (patch: Partial<Automation>) => api.setAutomation(patch),
    onMutate: async (patch) => {
      await qc.cancelQueries({ queryKey: ["automation"] });
      const prev = qc.getQueryData<Automation>(["automation"]);
      if (prev) qc.setQueryData<Automation>(["automation"], { ...prev, ...patch });
      return { prev };
    },
    onError: (_err, _patch, ctx) => {
      if (ctx?.prev) qc.setQueryData(["automation"], ctx.prev);
    },
    onSuccess: (data) => qc.setQueryData(["automation"], data),
  });
  return { ...query, update: mutation.mutate, updating: mutation.isPending, updateError: mutation.error };
}

export function useTaskAction(taskId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (action: ActionName) => api.action(taskId, action),
    onSuccess: (res) => {
      qc.setQueryData<TaskDetail>(["task", taskId], (old) => (old ? { ...old, task: res.task } : old));
      void qc.invalidateQueries({ queryKey: ["task", taskId] });
      void qc.invalidateQueries({ queryKey: ["board"] });
    },
  });
}
