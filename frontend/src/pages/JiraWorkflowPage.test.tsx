import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { api, type JiraRun } from "@/services/api";
import { renderWithProviders } from "@/test/render";
import { JiraWorkflowPage } from "./JiraWorkflowPage";
import { JiraRunTimeline } from "@/components/task/JiraRunTimeline";

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
    repair: { status: "passed", plan: { goal: "Avoid double booking", steps: ["Check capacity after awaiting"], acceptance_criteria: ["Only one reservation"], route: { id: "booking-backend", execution_agent: "workshop-booking-backend", qa_agent: "workshop-booking-qa" } }, qa: { verdict: "approved", summary: "Criteria met." }, summary: "Fixed race", patch: null, test_output: "2 passed", error: null },
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
  expect(tabs.map((tab) => tab.textContent?.trim())).toEqual(["Overview", "Timeline", "Drafts", "Plan", "Diff", "Validation", "Slack"]);
  fireEvent.mouseDown(within(sheet).getByRole("tab", { name: "Plan" }), { button: 0, ctrlKey: false });
  expect(within(sheet).getByText("Avoid double booking")).toBeInTheDocument();
  expect(within(sheet).getByText("workshop-booking-backend")).toBeInTheDocument();
  fireEvent.mouseDown(within(sheet).getByRole("tab", { name: "Validation" }), { button: 0, ctrlKey: false });
  expect(within(sheet).getByText("2 passed")).toBeInTheDocument();
  expect(within(sheet).getByText("Criteria met.")).toBeInTheDocument();

  fireEvent.click(within(sheet).getByRole("button", { name: "Close task details" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Double booking" })).toBeInTheDocument();
});

it("disables Start while a ready ticket is waiting for its plan", async () => {
  vi.spyOn(api, "jiraRuns").mockResolvedValue([{
    run_id: "run-4", issue_key: "LAB-4", title: "Waiting for a plan",
    source_kind: "training", state: "ready_for_handoff", repair_status: "running",
    last_error: null, thread_url: null,
  }]);
  vi.spyOn(api, "slackPairing").mockResolvedValue({ state: "idle", code: null, slack_user_id: null, reporter_id: null });
  renderWithProviders(<JiraWorkflowPage />);

  expect(await screen.findByRole("button", { name: "Планування…" })).toBeDisabled();
  expect(screen.queryByRole("button", { name: "Взяти в роботу" })).not.toBeInTheDocument();
});

it("expands tool input, the matching result and final JSON in Agent activity", () => {
  const base = {
    received_at: "2026-11-26T09:00:00Z", outcome: null, action: null, draft_version: null,
    stage: "review", agent_type: "workshop-reviewer", hook_status: null, status: null,
    attempt_id: "attempt-1",
  };
  const trace = { tool_name: "Read", tool_use_id: "tool-1", truncated: false, is_error: false };
  renderWithProviders(<JiraRunTimeline timeline={[
    { ...base, id: 1, event_type: "slack.thread_opened" },
    { ...base, id: 2, event_type: "workshop.agent_tool_use",
      trace: { ...trace, kind: "tool_use", detail: '{"file_path":"runbooks/static-page.md"}' } },
    { ...base, id: 3, event_type: "workshop.agent_tool_result",
      trace: { ...trace, kind: "tool_result", detail: "Page review runbook" } },
    { ...base, id: 4, event_type: "workshop.agent_structured_output",
      trace: { ...trace, tool_name: null, tool_use_id: null, kind: "structured_output", detail: '{"verdict":"approved"}' } },
  ]} />);
  expect(screen.getByText("Slack thread opened")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Agent activity" }));
  expect(screen.queryByText("Slack thread opened")).not.toBeInTheDocument();
  const read = screen.getByText("Read");
  fireEvent.click(read);
  const tool = read.closest("details")!;
  expect(tool).toHaveAttribute("open");
  expect(tool).toHaveTextContent('{"file_path":"runbooks/static-page.md"}');
  expect(tool).toHaveTextContent("Page review runbook");
  const output = screen.getByText("Structured output");
  fireEvent.click(output);
  expect(output.closest("details")).toHaveAttribute("open");
  expect(output.closest("details")).toHaveTextContent('{"verdict":"approved"}');
});

it("explains why an older run has no detailed tool logs", () => {
  renderWithProviders(<JiraRunTimeline timeline={[{
    id: 1, event_type: "workshop.agent_finished", received_at: "2026-11-26T09:00:00Z",
    outcome: null, action: null, draft_version: null, stage: "triage", agent_type: "workshop-triage",
    hook_status: "recorded", status: "succeeded",
  }]} />);
  fireEvent.click(screen.getByRole("button", { name: "Agent activity" }));
  expect(screen.getByText(/No tool details have been recorded/)).toBeInTheDocument();
  expect(screen.getByText("Agent finished", { exact: false })).toBeInTheDocument();
});

it("shows the blocker on the ticket and in Timeline with a link back to Slack", async () => {
  const reason = "The selected path is outside the available route.";
  const run: JiraRun = {
    run_id: "run-blocked", issue_key: "LAB-11", title: "Blocked page",
    source_kind: "training", state: "needs_intervention", repair_status: "failed",
    last_error: reason, thread_url: "https://example.slack.com/archives/C1/p123",
  };
  vi.spyOn(api, "jiraRuns").mockResolvedValue([run]);
  vi.spyOn(api, "slackPairing").mockResolvedValue({ state: "idle", code: null, slack_user_id: null, reporter_id: null });
  vi.spyOn(api, "jiraRun").mockResolvedValue({
    run, issue: null, reporter_slack_id: "U1", drafts: [], repair: null,
    timeline: [{
      id: 1, event_type: "workshop.blocker", received_at: "2026-11-26T08:00:00Z", status: "blocked",
      stage: "planning", outcome: null, action: null, draft_version: null, agent_type: null, hook_status: null,
      error: reason,
    }],
  });
  renderWithProviders(<JiraWorkflowPage />);
  fireEvent.click(await screen.findByRole("link", { name: "Blocked page" }));
  const sheet = within(await screen.findByRole("dialog", { name: "Blocked page" }));
  expect(sheet.getByRole("status")).toHaveTextContent(reason);
  expect(sheet.getByRole("link", { name: "Відкрити тред і відповісти на блокер у Slack" })).toHaveAttribute("href", run.thread_url);
  fireEvent.mouseDown(sheet.getByRole("tab", { name: "Timeline" }), { button: 0, ctrlKey: false });
  expect(sheet.getByRole("tabpanel")).toHaveTextContent(reason);
});

it("lets a paired reporter load the example, edit it and create a training issue", async () => {
  const example = { title: "Example booking bug", description_text: "The last seat was confirmed twice." };
  const page = { title: "Booking page", description_text: "Add a section for the waiting list." };
  const custom = { title: "Booking bug in two tabs", description_text: "Both browser tabs confirmed the same seat." };
  vi.spyOn(api, "jiraRuns").mockResolvedValue([]);
  vi.spyOn(api, "slackPairing").mockResolvedValue({
    state: "connected", code: null, slack_user_id: "U1", reporter_id: "reporter-1",
  });
  vi.spyOn(api, "trainingIssueTemplate").mockImplementation(async (name) => name === "static-page" ? page : example);
  const create = vi.spyOn(api, "createTrainingIssue").mockResolvedValue({
    ...custom, issue_key: "LAB-6", status: "new",
  });
  renderWithProviders(<JiraWorkflowPage />);

  fireEvent.click(await screen.findByRole("button", { name: "Create training issue" }));
  const form = within(screen.getByRole("dialog", { name: "Create training issue" }));
  expect(form.getByRole("button", { name: "Create issue" })).toBeDisabled();
  const exampleButton = form.getByRole("button", { name: "Use booking example" });
  await waitFor(() => expect(exampleButton).toBeEnabled());
  fireEvent.click(exampleButton);
  expect(form.getByLabelText("Description")).toHaveValue(example.description_text);
  const pageButton = form.getByRole("button", { name: "Use page example" });
  await waitFor(() => expect(pageButton).toBeEnabled());
  fireEvent.click(pageButton);
  expect(form.getByLabelText("Description")).toHaveValue(page.description_text);
  fireEvent.change(form.getByLabelText("Title"), { target: { value: custom.title } });
  fireEvent.change(form.getByLabelText("Description"), { target: { value: custom.description_text } });
  fireEvent.click(form.getByRole("button", { name: "Create issue" }));

  expect(await screen.findByText(/Created LAB-6/)).toHaveAttribute("role", "status");
  expect(create).toHaveBeenCalledExactlyOnceWith("reporter-1", custom);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});
