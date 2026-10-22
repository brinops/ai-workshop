import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { STREAM_URL, type EventOut, type LogLineOut } from "@/services/api";
import { StreamContext, type StreamApi, type StreamStatus } from "./stream-context";

const REFETCH_DEBOUNCE_MS = 300;
/**
 * The worker updates `task.activity` without emitting an event, so agent log traffic is
 * also used (at a slower cadence) as a hint to refresh the board and the affected task.
 */
const LOG_REFRESH_MS = 1500;
const HEALTH_EVENTS = new Set(["agent_started", "agent_finished", "worker_started", "worker_stopped"]);

/**
 * One EventSource for the whole app. Task events trigger (debounced) refetches of the board,
 * the global feed and affected task details; agent log lines are fanned out to subscribers.
 * EventSource reconnects on its own and resumes from Last-Event-ID.
 */
export function StreamProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [status, setStatus] = useState<StreamStatus>("connecting");
  const [lastMessageAt, setLastMessageAt] = useState<number | null>(null);
  const logSubs = useRef(new Set<(lines: LogLineOut[]) => void>());
  const eventSubs = useRef(new Set<(e: EventOut) => void>());
  const pending = useRef({ tasks: new Set<number>(), global: false, health: false, automation: false });
  const timer = useRef<number | null>(null);
  const logTimer = useRef<number | null>(null);
  const logTasks = useRef<Set<number>>(new Set());

  const flush = useCallback(() => {
    timer.current = null;
    const p = pending.current;
    pending.current = { tasks: new Set(), global: false, health: false, automation: false };
    void qc.invalidateQueries({ queryKey: ["board"] });
    void qc.invalidateQueries({ queryKey: ["events"] });
    for (const id of p.tasks) void qc.invalidateQueries({ queryKey: ["task", id] });
    if (p.health) void qc.invalidateQueries({ queryKey: ["health"] });
    if (p.automation) void qc.invalidateQueries({ queryKey: ["automation"] });
  }, [qc]);

  const schedule = useCallback(() => {
    if (timer.current === null) timer.current = window.setTimeout(flush, REFETCH_DEBOUNCE_MS);
  }, [flush]);

  useEffect(() => {
    if (typeof EventSource === "undefined") return;
    const es = new EventSource(STREAM_URL);
    let everOpened = false;

    es.addEventListener("open", () => {
      setStatus("open");
      if (everOpened) {
        // Back after a drop: refresh everything in case we missed state.
        pending.current.global = true;
        pending.current.health = true;
        schedule();
      }
      everOpened = true;
    });
    es.addEventListener("error", () => {
      setStatus(es.readyState === EventSource.CLOSED ? "reconnecting" : everOpened ? "reconnecting" : "connecting");
    });
    es.addEventListener("hello", () => {
      setStatus("open");
      setLastMessageAt(Date.now());
    });
    es.addEventListener("task_event", (msg) => {
      setLastMessageAt(Date.now());
      let ev: EventOut;
      try {
        ev = JSON.parse((msg as MessageEvent<string>).data) as EventOut;
      } catch {
        return;
      }
      if (ev.task_id !== null) pending.current.tasks.add(ev.task_id);
      if (HEALTH_EVENTS.has(ev.type)) pending.current.health = true;
      if (ev.type === "settings_changed") pending.current.automation = true;
      schedule();
      for (const fn of eventSubs.current) fn(ev);
    });
    es.addEventListener("task_changed", (msg) => {
      setLastMessageAt(Date.now());
      try {
        const { task_ids } = JSON.parse((msg as MessageEvent<string>).data) as { task_ids: number[] };
        for (const id of task_ids) pending.current.tasks.add(id);
      } catch {
        return;
      }
      schedule();
    });
    es.addEventListener("agent_log", (msg) => {
      setLastMessageAt(Date.now());
      let lines: LogLineOut[];
      try {
        lines = JSON.parse((msg as MessageEvent<string>).data) as LogLineOut[];
      } catch {
        return;
      }
      for (const fn of logSubs.current) fn(lines);
      // Refresh only the tasks these lines belong to (throttled; agents can be chatty).
      for (const line of lines) logTasks.current.add(line.task_id);
      if (logTimer.current === null) {
        logTimer.current = window.setTimeout(() => {
          logTimer.current = null;
          void qc.invalidateQueries({ queryKey: ["board"] });
          for (const id of logTasks.current) void qc.invalidateQueries({ queryKey: ["task", id] });
          logTasks.current.clear();
        }, LOG_REFRESH_MS);
      }
    });

    return () => {
      es.close();
      if (timer.current !== null) window.clearTimeout(timer.current);
      if (logTimer.current !== null) window.clearTimeout(logTimer.current);
      timer.current = null;
      logTimer.current = null;
    };
  }, [schedule, qc]);

  const subscribeLogs = useCallback((fn: (lines: LogLineOut[]) => void) => {
    logSubs.current.add(fn);
    return () => {
      logSubs.current.delete(fn);
    };
  }, []);

  const subscribeEvents = useCallback((fn: (e: EventOut) => void) => {
    eventSubs.current.add(fn);
    return () => {
      eventSubs.current.delete(fn);
    };
  }, []);

  const value = useMemo<StreamApi>(
    () => ({ status, lastMessageAt, subscribeLogs, subscribeEvents }),
    [status, lastMessageAt, subscribeLogs, subscribeEvents],
  );

  return <StreamContext.Provider value={value}>{children}</StreamContext.Provider>;
}
