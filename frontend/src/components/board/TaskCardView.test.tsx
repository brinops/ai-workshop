import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderWithProviders } from "@/test/render";
import type { TaskCard } from "@/services/api";
import { TaskCardView } from "./TaskCardView";

const base: TaskCard = {
  id: 7,
  repo: "acme/platform",
  pr_number: 42,
  pr_url: "https://github.com/acme/platform/pull/42",
  title: "Bump web chart replicas",
  author: "dev",
  head_branch: "feat/web-replicas",
  base_branch: "main",
  head_sha: "abcdef1234567890",
  expected_sha: "abcdef1234567890",
  source: "hook",
  route: "helm-validate",
  state: "IN_PROGRESS",
  column: "IN_PROGRESS",
  pending_action: null,
  paused: false,
  cancel_requested: false,
  resolution: null,
  classification: "SCHEMA_VIOLATION",
  confidence: 0.92,
  root_cause: null,
  ci_status: "failure",
  ci_checked_at: "2026-10-22T11:59:00Z",
  ci_waiting_since: null,
  ci_next_check_at: null,
  attempt: 1,
  max_attempts: 2,
  activity: "Running helm lint in the worktree",
  cost_usd: 0.316,
  agent_runs: 2,
  agent_running: true,
  last_error: null,
  created_at: "2026-10-22T11:50:00Z",
  updated_at: "2026-10-22T11:59:30Z",
};

describe("TaskCardView", () => {
  it("shows state, CI, classification, attempts and live agent activity", () => {
    renderWithProviders(<TaskCardView task={base} now={Date.parse("2026-10-22T12:00:00Z")} selected={false} />);
    expect(screen.getByText("IN_PROGRESS")).toBeInTheDocument();
    expect(screen.getByText("CI failed")).toBeInTheDocument();
    expect(screen.getByText("Schema violation")).toBeInTheDocument();
    expect(screen.getByText("attempt 1/2")).toBeInTheDocument();
    expect(screen.getByText(/\$0.32 · 2 runs/)).toBeInTheDocument();
    expect(screen.getByText(/Running helm lint in the worktree/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Bump web chart replicas" })).toHaveAttribute("href", "/tasks/7");
    expect(screen.getByText("updated 30s ago")).toBeInTheDocument();
  });

  it("offers the approve-push button when a push is awaiting approval", () => {
    renderWithProviders(
      <TaskCardView task={{ ...base, agent_running: false, pending_action: "push" }} now={Date.now()} selected={false} />,
    );
    expect(screen.getByText("Awaiting push approval")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve push for PR #42" })).toBeEnabled();
    expect(screen.queryByText(/Agent working/)).not.toBeInTheDocument();
  });
});
