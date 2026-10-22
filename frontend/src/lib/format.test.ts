import { describe, expect, it } from "vitest";
import { durationBetween, formatCost, formatDuration, humanize, parseTs, relativeTime, shortSha } from "./format";

const NOW = Date.parse("2026-10-22T12:00:00Z");

describe("relativeTime", () => {
  it("formats recent timestamps", () => {
    expect(relativeTime("2026-10-22T12:00:00Z", NOW)).toBe("just now");
    expect(relativeTime("2026-10-22T11:59:30Z", NOW)).toBe("30s ago");
    expect(relativeTime("2026-10-22T11:55:00Z", NOW)).toBe("5m ago");
    expect(relativeTime("2026-10-22T09:00:00Z", NOW)).toBe("3h ago");
    expect(relativeTime("2026-10-20T12:00:00Z", NOW)).toBe("2d ago");
  });

  it("handles missing values and zone-less timestamps", () => {
    expect(relativeTime(null, NOW)).toBe("—");
    expect(parseTs("2026-10-22T12:00:00")).toBe(NOW);
  });
});

describe("formatDuration", () => {
  it("formats seconds, minutes and hours", () => {
    expect(formatDuration(4.9)).toBe("4s");
    expect(formatDuration(65)).toBe("1m 05s");
    expect(formatDuration(3 * 3600 + 7 * 60)).toBe("3h 07m");
    expect(formatDuration(-1)).toBe("—");
  });

  it("computes durations between timestamps", () => {
    expect(durationBetween("2026-10-22T11:58:00Z", "2026-10-22T11:59:30Z")).toBe("1m 30s");
    expect(durationBetween("2026-10-22T11:59:50Z", null, NOW)).toBe("10s");
  });
});

describe("misc formatters", () => {
  it("shortens shas, costs and enum names", () => {
    expect(shortSha("abcdef1234567")).toBe("abcdef1");
    expect(formatCost(0.1234)).toBe("$0.12");
    expect(formatCost(0.004)).toBe("$0.0040");
    expect(humanize("LOGICAL_CONFIGURATION_ERROR")).toBe("Logical configuration error");
  });
});
