import { Bot, Monitor, MonitorOff, Moon, Radio, Sun } from "lucide-react";
import { NavLink, useMatch } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";
import { useHealth } from "@/hooks/queries";
import { useStream } from "@/hooks/stream-context";
import { cn } from "@/lib/utils";

const COMPONENTS: { key: string; label: string }[] = [
  { key: "worker", label: "Worker" },
  { key: "github", label: "GitHub" },
  { key: "claude", label: "Claude" },
  { key: "helm", label: "helm" },
  { key: "kubeconform", label: "kubeconform" },
  { key: "slack", label: "Slack" },
];

function HealthDots() {
  const { data, isError, isLoading } = useHealth();
  if (isError) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-md border border-bad/40 bg-bad/10 px-2 py-1 text-xs text-bad">
        <span className="size-2 rounded-full bg-bad" aria-hidden /> Backend unreachable
      </span>
    );
  }
  return (
    <ul className="flex items-center gap-1" aria-label="System health">
      {COMPONENTS.map(({ key, label }) => {
        const c = data?.components[key];
        const state = isLoading || !c ? "unknown" : c.ok ? "ok" : "down";
        return (
          <li key={key}>
            <Tooltip
              content={
                <span>
                  <span className="font-medium">{label}</span>:{" "}
                  {state === "unknown" ? "checking…" : state === "ok" ? "OK" : "unavailable"}
                  {c?.detail && <span className="block font-mono text-[0.7rem] text-muted">{c.detail}</span>}
                </span>
              }
            >
              <span
                tabIndex={0}
                className="inline-flex items-center gap-1.5 rounded-md px-1.5 py-1 text-xs text-muted hover:bg-raised"
                aria-label={`${label}: ${state === "ok" ? "OK" : state === "down" ? `unavailable — ${c?.detail ?? ""}` : "checking"}`}
              >
                <span
                  className={cn(
                    "size-2 rounded-full",
                    state === "ok" && "bg-ok",
                    state === "down" && "bg-bad",
                    state === "unknown" && "bg-line-strong",
                  )}
                  aria-hidden
                />
                <span className="hidden xl:inline">{label}</span>
              </span>
            </Tooltip>
          </li>
        );
      })}
    </ul>
  );
}

function ConnectionIndicator() {
  const { status } = useStream();
  const label = status === "open" ? "Live" : status === "connecting" ? "Connecting…" : "Reconnecting…";
  return (
    <Tooltip
      content={
        status === "open"
          ? "Receiving live events from the control plane"
          : "The live event stream dropped — the browser is reconnecting automatically"
      }
    >
      <span
        tabIndex={0}
        role="status"
        className={cn(
          "inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs font-medium",
          status === "open" ? "border-ok/30 text-ok" : "border-warn/40 text-warn",
        )}
      >
        <Radio className={cn("size-3.5", status !== "open" && "animate-pulse-dot")} aria-hidden />
        {label}
      </span>
    </Tooltip>
  );
}

export function TopBar({
  presenting,
  onTogglePresenting,
  light,
  onToggleTheme,
}: {
  presenting: boolean;
  onTogglePresenting: () => void;
  light: boolean;
  onToggleTheme: () => void;
}) {
  const { data: health } = useHealth();
  const jiraWorkflow = useMatch("/jira-workflow");
  const agents = health?.agents_running ?? 0;
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-bg/85 backdrop-blur">
      <div className="flex h-14 items-center gap-4 px-5">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="flex size-7 shrink-0 items-center justify-center rounded-md border border-accent/40 bg-accent/10" aria-hidden>
            <svg viewBox="0 0 32 32" className="size-4">
              <path d="M7 17l6 6L25 9" fill="none" stroke="var(--accent)" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
          <h1 className="truncate text-[0.98rem] font-semibold tracking-tight">CI Control Plane</h1>
        </div>

        <div className="ml-auto flex items-center gap-3">
          {!presenting && <HealthDots />}
          <Tooltip content={health ? `Model: ${health.model}` : "Agents currently running"}>
            <span
              tabIndex={0}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs font-medium tabular-nums",
                agents > 0 ? "border-accent/40 bg-accent/10 text-accent" : "border-line text-muted",
              )}
            >
              <Bot className={cn("size-3.5", agents > 0 && "animate-pulse-dot")} aria-hidden />
              {agents} {agents === 1 ? "agent" : "agents"} running
            </span>
          </Tooltip>
          <ConnectionIndicator />
          <Button variant="ghost" size="icon" onClick={onToggleTheme} aria-label={light ? "Switch to dark theme" : "Switch to light theme"}>
            {light ? <Moon /> : <Sun />}
          </Button>
          {!jiraWorkflow && <Button
            variant={presenting ? "primary" : "default"}
            size="md"
            onClick={onTogglePresenting}
            aria-pressed={presenting}
          >
            {presenting ? <MonitorOff /> : <Monitor />}
            {presenting ? "Exit presentation" : "Presentation mode"}
          </Button>}
        </div>
      </div>
      <nav aria-label="Dashboards" className="flex gap-5 px-5 text-sm">
        {[{ path: "/", label: "CI Dashboard" }, { path: "/jira-workflow", label: "Jira Workflow" }].map(({ path, label }) => (
          <NavLink key={path} to={path} className={() => cn(
            "border-b-2 px-1 py-2 font-medium hover:text-fg",
            (path === "/jira-workflow" ? jiraWorkflow : !jiraWorkflow)
              ? "border-accent text-fg" : "border-transparent text-muted",
          )}>
            {label}
          </NavLink>
        ))}
      </nav>
    </header>
  );
}
