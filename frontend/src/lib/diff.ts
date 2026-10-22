/** Minimal unified-diff parser (git diff / diff -u output). */

export type DiffLineType = "add" | "del" | "context" | "meta";

export interface DiffLine {
  type: DiffLineType;
  text: string;
  oldNo: number | null;
  newNo: number | null;
}

export interface DiffHunk {
  header: string;
  lines: DiffLine[];
}

export interface DiffFile {
  oldPath: string | null;
  newPath: string | null;
  /** Display path: new path, or old path for deletions. */
  path: string;
  status: "added" | "deleted" | "modified" | "renamed";
  additions: number;
  deletions: number;
  hunks: DiffHunk[];
}

const HUNK_RE = /^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$/;

function cleanPath(p: string): string | null {
  const path = p.trim().split("\t")[0];
  if (path === "/dev/null") return null;
  return path.replace(/^[ab]\//, "");
}

function newFile(oldPath: string | null, newPath: string | null): DiffFile {
  return { oldPath, newPath, path: "", status: "modified", additions: 0, deletions: 0, hunks: [] };
}

function finalize(f: DiffFile): DiffFile {
  if (f.oldPath === null && f.newPath !== null) f.status = "added";
  else if (f.newPath === null && f.oldPath !== null) f.status = "deleted";
  else if (f.oldPath && f.newPath && f.oldPath !== f.newPath) f.status = "renamed";
  else f.status = "modified";
  f.path = f.newPath ?? f.oldPath ?? "(unknown file)";
  return f;
}

/**
 * Parses a unified diff into files → hunks → numbered lines.
 * Hunk bodies are consumed using the line counts in the `@@` header, so content lines that
 * happen to look like headers (e.g. a removed YAML `-- ` line) are not misread.
 */
export function parseUnifiedDiff(input: string): DiffFile[] {
  const files: DiffFile[] = [];
  if (!input || !input.trim()) return files;

  let file: DiffFile | null = null;
  let hunk: DiffHunk | null = null;
  let oldNo = 0;
  let newNo = 0;
  let oldLeft = 0;
  let newLeft = 0;
  let sawGitHeader = false;

  const lines = input.replace(/\r\n/g, "\n").split("\n");
  for (const raw of lines) {
    const inHunk = hunk !== null && (oldLeft > 0 || newLeft > 0);

    if (inHunk && hunk && file) {
      if (raw.startsWith("+")) {
        hunk.lines.push({ type: "add", text: raw.slice(1), oldNo: null, newNo: newNo++ });
        file.additions++;
        newLeft--;
      } else if (raw.startsWith("-")) {
        hunk.lines.push({ type: "del", text: raw.slice(1), oldNo: oldNo++, newNo: null });
        file.deletions++;
        oldLeft--;
      } else if (raw.startsWith("\\")) {
        hunk.lines.push({ type: "meta", text: raw, oldNo: null, newNo: null });
      } else {
        // Context line (an empty string is a context line whose leading space was stripped).
        hunk.lines.push({ type: "context", text: raw.slice(1), oldNo: oldNo++, newNo: newNo++ });
        oldLeft--;
        newLeft--;
      }
      continue;
    }

    if (raw.startsWith("\\") && hunk) {
      hunk.lines.push({ type: "meta", text: raw, oldNo: null, newNo: null });
      continue;
    }

    if (raw.startsWith("diff --git ")) {
      const m = /^diff --git a\/(.+?) b\/(.+)$/.exec(raw);
      file = newFile(m ? m[1] : null, m ? m[2] : null);
      files.push(file);
      hunk = null;
      sawGitHeader = true;
      continue;
    }

    if (raw.startsWith("--- ")) {
      // Plain `diff -u` output has no `diff --git` line: each `---` starts a new file.
      if (!file || !sawGitHeader || file.hunks.length > 0) {
        file = newFile(null, null);
        files.push(file);
        hunk = null;
        sawGitHeader = false;
      }
      file.oldPath = cleanPath(raw.slice(4));
      continue;
    }

    if (raw.startsWith("+++ ") && file) {
      file.newPath = cleanPath(raw.slice(4));
      continue;
    }

    const hm = HUNK_RE.exec(raw);
    if (hm) {
      if (!file) {
        file = newFile(null, null);
        files.push(file);
      }
      oldNo = Number(hm[1]);
      newNo = Number(hm[3]);
      oldLeft = hm[2] === undefined ? 1 : Number(hm[2]);
      newLeft = hm[4] === undefined ? 1 : Number(hm[4]);
      hunk = { header: raw, lines: [] };
      file.hunks.push(hunk);
      continue;
    }

    if (file && !hunk) {
      if (raw.startsWith("new file mode")) file.oldPath = null;
      else if (raw.startsWith("deleted file mode")) file.newPath = null;
      else if (raw.startsWith("rename from ")) file.oldPath = raw.slice("rename from ".length);
      else if (raw.startsWith("rename to ")) file.newPath = raw.slice("rename to ".length);
    }
  }

  return files.map(finalize);
}
