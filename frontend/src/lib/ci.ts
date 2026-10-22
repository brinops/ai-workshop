import type { CISnapshotOut } from "@/services/api";

/** Group snapshots by commit, newest commit first. */
export function groupBySha(ci: CISnapshotOut[]): CISnapshotOut[][] {
  const groups = new Map<string, CISnapshotOut[]>();
  for (const s of [...ci].sort((a, b) => a.id - b.id)) {
    const g = groups.get(s.sha) ?? [];
    g.push(s);
    groups.set(s.sha, g);
  }
  return [...groups.values()].sort((a, b) => b[b.length - 1].id - a[a.length - 1].id);
}
