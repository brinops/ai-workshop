/** Formatting helpers. All backend timestamps are UTC ISO strings. */

export function parseTs(ts: string | null | undefined): number | null {
  if (!ts) return null;
  // Tolerate timestamps without a zone designator by treating them as UTC.
  const normalized = /[zZ]|[+-]\d\d:?\d\d$/.test(ts) ? ts : `${ts}Z`;
  const ms = Date.parse(normalized);
  return Number.isNaN(ms) ? null : ms;
}

export function relativeTime(ts: string | null | undefined, now: number = Date.now()): string {
  const ms = parseTs(ts);
  if (ms === null) return "—";
  const diff = Math.round((now - ms) / 1000);
  if (diff < 0) return diff > -5 ? "just now" : "in the future";
  if (diff < 5) return "just now";
  if (diff < 60) return `${diff}s ago`;
  const min = Math.floor(diff / 60);
  if (min < 60) return `${min}m ago`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

/** Duration in seconds -> "4s", "1m 05s", "2h 03m". */
export function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "—";
  const s = Math.floor(seconds);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${String(s % 60).padStart(2, "0")}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${String(m % 60).padStart(2, "0")}m`;
}

export function durationBetween(start: string | null | undefined, end: string | null | undefined, now: number = Date.now()): string {
  const a = parseTs(start);
  if (a === null) return "—";
  const b = end ? parseTs(end) : now;
  if (b === null) return "—";
  return formatDuration((b - a) / 1000);
}

export function absoluteTime(ts: string | null | undefined): string {
  const ms = parseTs(ts);
  if (ms === null) return "—";
  return new Date(ms).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function clockTime(ts: string | null | undefined): string {
  const ms = parseTs(ts);
  if (ms === null) return "—";
  return new Date(ms).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function shortSha(sha: string | null | undefined, n = 7): string {
  return sha ? sha.slice(0, n) : "—";
}

export function formatCost(usd: number | null | undefined): string {
  if (usd === null || usd === undefined) return "—";
  return usd < 0.01 ? `$${usd.toFixed(4)}` : `$${usd.toFixed(2)}`;
}

export function formatPercent(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `${Math.round(v * 100)}%`;
}

/** "LOGICAL_CONFIGURATION_ERROR" -> "Logical configuration error" */
export function humanize(value: string | null | undefined): string {
  if (!value) return "—";
  const s = value.replace(/[_-]+/g, " ").toLowerCase().trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}
