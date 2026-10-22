/** Text / ring classes for event severity levels. */

export function levelColor(level: string): string {
  switch (level) {
    case "success":
      return "text-ok";
    case "warning":
      return "text-warn";
    case "error":
      return "text-bad";
    default:
      return "text-muted";
  }
}

export function levelRing(level: string): string {
  switch (level) {
    case "success":
      return "border-ok/40 bg-ok/10";
    case "warning":
      return "border-warn/40 bg-warn/10";
    case "error":
      return "border-bad/40 bg-bad/10";
    default:
      return "border-line-strong bg-raised";
  }
}
