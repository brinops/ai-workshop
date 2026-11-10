import { fireEvent, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { api, type JiraRun } from "@/services/api";
import { renderWithProviders } from "@/test/render";
import { JiraWorkflowPage } from "./JiraWorkflowPage";

vi.mock("@/components/layout/TopBar", () => ({ TopBar: () => null }));

it("opens a Jira card in the right sheet and keeps the board visible after closing it", async () => {
  const run: JiraRun = {
    run_id: "run-3", issue_key: "LAB-3", title: "Double booking",
    source_kind: "training", state: "in_progress", repair_status: "passed",
    last_error: null, thread_url: "https://example.slack.com/archives/C1/p123",
  };
  vi.spyOn(api, "jiraRuns").mockResolvedValue([run]);
  vi.spyOn(api, "slackPairing").mockResolvedValue({ state: "idle", code: null, slack_user_id: null, reporter_id: null });
  vi.spyOn(api, "jiraRun").mockResolvedValue({
    run, reporter_slack_id: "U1",
    issue: { issue_key: "LAB-3", title: "Double booking", status: "new", description_text: "Booking issue." },
    drafts: [{ version: 1, status: "approved", decision: "approve", decided_at: null }],
    timeline: [],
    repair: { status: "passed", summary: "Fixed race", patch: null, test_output: "2 passed", error: null },
  });
  renderWithProviders(<JiraWorkflowPage />);

  const card = await screen.findByRole("link", { name: "Double booking" });
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  fireEvent.click(card);

  const sheet = await screen.findByRole("dialog", { name: "Double booking" });
  expect(sheet).toHaveClass("right-0");
  expect(within(sheet).getByText("Jira New")).toBeInTheDocument();
  expect(within(sheet).getByRole("button", { name: "Завершити" })).toBeEnabled();
  const tabs = within(sheet).getAllByRole("tab");
  expect(tabs.map((tab) => tab.textContent?.trim())).toEqual(["Overview", "Timeline", "Drafts", "Diff", "Validation", "Slack"]);
  fireEvent.mouseDown(within(sheet).getByRole("tab", { name: "Validation" }), { button: 0, ctrlKey: false });
  expect(within(sheet).getByText("2 passed")).toBeInTheDocument();

  fireEvent.click(within(sheet).getByRole("button", { name: "Close task details" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Double booking" })).toBeInTheDocument();
});
