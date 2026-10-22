import { fireEvent, render, screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/render";
import { describe, expect, it } from "vitest";
import { Timeline } from "./TimelineTab";
import { ValidationTab } from "./ValidationTab";
import type { CISnapshotOut, EventOut } from "@/services/api";

const event: EventOut = {
  id: 7, task_id: 1, ts: "2026-10-22T12:00:00Z", type: "ci_status", level: "error",
  message: "CI on 9f0b884: failure", data: { sha: "9f0b884", overall: "failure" },
};

describe("Timeline", () => {
  it("expands an event to show its recorded data", () => {
    render(<Timeline events={[event]} />);
    expect(screen.queryByText("Event id")).toBeNull();
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    expect(screen.getByText("Event id")).toBeTruthy();
    expect(screen.getByText("9f0b884")).toBeTruthy();
  });
});

describe("ValidationTab", () => {
  const check = (verdict: string) => ({ name: "helm-validate", verdict, conclusion: null, html_url: null });
  const ci: CISnapshotOut[] = [
    { id: 1, sha: "aaa", overall: "pending", checks: [check("pending")], ts: "2026-10-22T12:00:00Z" },
    { id: 2, sha: "aaa", overall: "failure", checks: [check("failure")], ts: "2026-10-22T12:00:10Z" },
  ];

  it("does not animate historical pending observations", () => {
    const { container } = renderWithProviders(<ValidationTab validations={[]} ci={ci} trackedSha="aaa" waitingForCi={false} />);
    expect(container.querySelector(".animate-spin")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /status history/i }));
    expect(container.querySelector(".animate-spin")).toBeNull();
  });

  it("animates only while the tracked commit is pending", () => {
    const pending = [{ ...ci[0] }];
    const { container } = renderWithProviders(<ValidationTab validations={[]} ci={pending} trackedSha="aaa" waitingForCi />);
    expect(container.querySelector(".animate-spin")).not.toBeNull();
    expect(screen.getByText("live")).toBeTruthy();
  });
});
