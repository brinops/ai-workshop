import { describe, expect, it } from "vitest";
import { groupBySha } from "./ci";
import type { CISnapshotOut } from "@/services/api";

const snap = (id: number, sha: string, overall: string): CISnapshotOut => ({ id, sha, overall, checks: [], ts: "2026-10-22T12:00:00Z" });

describe("groupBySha", () => {
  it("groups observations per commit, newest commit first, oldest observation first", () => {
    const groups = groupBySha([snap(1, "aaa", "pending"), snap(2, "aaa", "failure"), snap(3, "fff", "pending"), snap(4, "fff", "success")]);
    expect(groups.map((g) => g[0].sha)).toEqual(["fff", "aaa"]);
    expect(groups[1].map((s) => s.overall)).toEqual(["pending", "failure"]);
    expect(groups[0][groups[0].length - 1].overall).toBe("success");
  });
});
