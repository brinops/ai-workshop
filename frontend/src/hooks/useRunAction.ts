import { useToast } from "@/components/ui/toast";
import { ACTION_META } from "@/lib/actions";
import { ApiError, type ActionName } from "@/services/api";
import { useTaskAction } from "./queries";

/** Task action mutation with success/error toasts (409s surface the backend's reason). */
export function useRunAction(taskId: number) {
  const { toast } = useToast();
  const mutation = useTaskAction(taskId);
  const run = (action: ActionName) =>
    mutation.mutate(action, {
      onSuccess: (res) => toast({ tone: "success", title: ACTION_META[action].pastTense, description: res.message }),
      onError: (err) =>
        toast({
          tone: "error",
          title: err instanceof ApiError && err.status === 409 ? `${ACTION_META[action].label} isn't available` : `${ACTION_META[action].label} failed`,
          description: err.message,
        }),
    });
  return { run, pending: mutation.isPending ? mutation.variables : null };
}
