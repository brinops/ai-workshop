import { createContext, useContext } from "react";
import type { EventOut, LogLineOut } from "@/services/api";

export type StreamStatus = "connecting" | "open" | "reconnecting";

export interface StreamApi {
  status: StreamStatus;
  /** Timestamp (ms) of the last message received from the stream. */
  lastMessageAt: number | null;
  /** Subscribe to agent log lines; returns an unsubscribe function. */
  subscribeLogs: (fn: (lines: LogLineOut[]) => void) => () => void;
  /** Subscribe to task events as they arrive. */
  subscribeEvents: (fn: (event: EventOut) => void) => () => void;
}

export const StreamContext = createContext<StreamApi | null>(null);

export function useStream(): StreamApi {
  const ctx = useContext(StreamContext);
  if (!ctx) throw new Error("useStream must be used inside <StreamProvider>");
  return ctx;
}
