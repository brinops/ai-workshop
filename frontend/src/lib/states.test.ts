import { describe, expect, it } from "vitest";
import type { TaskCard } from "@/services/api";
import { columnOf, pickSpotlight, pipelineStageOf, statesInColumn } from "./states";

describe("column mapping", () => {
  it("mirrors the backend COLUMN_OF mapping", () => {
    expect(statesInColumn("NEW")).toEqual(["NEW", "WAITING_CI", "ANALYZING"]);
    expect(statesInColumn("TODO")).toEqual(["TODO", "NEEDS_REVIEW"]);
    expect(statesInColumn("IN_PROGRESS")).toEqual(["IN_PROGRESS", "VALIDATING"]);
    expect(statesInColumn("DONE")).toEqual(["DONE", "FAILED"]);
    expect(columnOf("NEEDS_REVIEW")).toBe("TODO");
    expect(columnOf("SOMETHING_ELSE")).toBe("NEW");
  });

  it("maps states to pipeline stages", () => {
    expect(pipelineStageOf("WAITING_CI")).toBe("detection");
    expect(pipelineStageOf("ANALYZING")).toBe("reasoning");
    expect(pipelineStageOf("IN_PROGRESS")).toBe("repair");
    expect(pipelineStageOf("VALIDATING")).toBe("validation");
    expect(pipelineStageOf("DONE")).toBe("visibility");
  });
});

describe("pickSpotlight", () => {
  const t = (id: number, state: TaskCard["state"], updated_at: string, agent_running = false) =>
    ({ id, state, updated_at, agent_running }) as TaskCard;

  it("prefers a running agent, then the newest active task, then the newest task", () => {
    expect(pickSpotlight([])).toBeNull();
    expect(pickSpotlight([t(1, "DONE", "2026-01-02T00:00:00Z"), t(2, "TODO", "2026-01-01T00:00:00Z")])?.id).toBe(2);
    expect(
      pickSpotlight([t(1, "TODO", "2026-01-03T00:00:00Z"), t(2, "IN_PROGRESS", "2026-01-01T00:00:00Z", true)])?.id,
    ).toBe(2);
    expect(pickSpotlight([t(1, "DONE", "2026-01-02T00:00:00Z"), t(2, "FAILED", "2026-01-03T00:00:00Z")])?.id).toBe(2);
  });
});

describe("pipelineStatuses", () => {
  it("never marks stages done that the state does not prove", async () => {
    const { pipelineStatuses } = await import("./states");
    expect(pipelineStatuses("IN_PROGRESS")).toEqual({
      detection: "done",
      reasoning: "done",
      repair: "active",
      validation: "idle",
      visibility: "idle",
    });
    expect(pipelineStatuses("NEEDS_REVIEW").repair).toBe("idle");
    expect(pipelineStatuses("NEEDS_REVIEW").visibility).toBe("stopped");
    expect(pipelineStatuses("DONE", "passed_without_remediation").repair).toBe("idle");
    expect(pipelineStatuses("DONE", "remediated").repair).toBe("done");
  });
});
