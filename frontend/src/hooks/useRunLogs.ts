import { useEffect, useState } from "react";
import { api, type LogLineOut } from "@/services/api";
import { useStream } from "./stream-context";

const PAGE = 2000;

interface RunLogsState {
  key: string;
  lines: LogLineOut[];
  loading: boolean;
  error: string | null;
}

function merge(existing: LogLineOut[], incoming: LogLineOut[]): LogLineOut[] {
  if (incoming.length === 0) return existing;
  const lastId = existing.length ? existing[existing.length - 1].id : 0;
  const fresh = incoming.filter((l) => l.id > lastId);
  if (fresh.length === incoming.length && fresh.length > 0) return [...existing, ...fresh];
  // Out-of-order or overlapping delivery: merge by id.
  const byId = new Map(existing.map((l) => [l.id, l]));
  for (const l of incoming) byId.set(l.id, l);
  return [...byId.values()].sort((a, b) => a.id - b.id);
}

/** Loads the log of one agent run, then live-appends lines arriving on the SSE stream. */
export function useRunLogs(taskId: number, runId: number | null) {
  const { subscribeLogs } = useStream();
  const key = `${taskId}:${runId ?? "none"}`;
  const [state, setState] = useState<RunLogsState>({ key, lines: [], loading: runId !== null, error: null });

  // Reset when switching runs (state derived from props, React-recommended pattern).
  if (state.key !== key) {
    setState({ key, lines: [], loading: runId !== null, error: null });
  }

  useEffect(() => {
    if (runId === null) return;
    let cancelled = false;
    const unsubscribe = subscribeLogs((lines) => {
      const mine = lines.filter((l) => l.run_id === runId);
      if (mine.length && !cancelled) setState((s) => (s.key === key ? { ...s, lines: merge(s.lines, mine) } : s));
    });
    (async () => {
      try {
        let after = 0;
        for (;;) {
          const page = await api.runLogs(taskId, runId, after);
          if (cancelled) return;
          setState((s) => (s.key === key ? { ...s, lines: merge(s.lines, page) } : s));
          if (page.length < PAGE) break;
          after = page[page.length - 1].id;
        }
        if (!cancelled) setState((s) => (s.key === key ? { ...s, loading: false } : s));
      } catch (e) {
        if (!cancelled) setState((s) => (s.key === key ? { ...s, loading: false, error: (e as Error).message } : s));
      }
    })();
    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [taskId, runId, key, subscribeLogs]);

  return { lines: state.lines, loading: state.loading, error: state.error };
}
