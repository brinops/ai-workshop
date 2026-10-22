import { describe, expect, it } from "vitest";
import { parseUnifiedDiff } from "./diff";

const GIT_DIFF = `diff --git a/charts/web/values.yaml b/charts/web/values.yaml
index 1111111..2222222 100644
--- a/charts/web/values.yaml
+++ b/charts/web/values.yaml
@@ -3,4 +3,4 @@ image:
   repository: nginx
 service:
-  port: "eighty"
+  port: 80
   type: ClusterIP
diff --git a/charts/web/templates/new.yaml b/charts/web/templates/new.yaml
new file mode 100644
--- /dev/null
+++ b/charts/web/templates/new.yaml
@@ -0,0 +1,2 @@
+---
+kind: ConfigMap
`;

describe("parseUnifiedDiff", () => {
  it("returns no files for empty input", () => {
    expect(parseUnifiedDiff("")).toEqual([]);
    expect(parseUnifiedDiff("  \n")).toEqual([]);
  });

  it("parses files, hunks, counts and line numbers", () => {
    const files = parseUnifiedDiff(GIT_DIFF);
    expect(files).toHaveLength(2);

    const [values, created] = files;
    expect(values.path).toBe("charts/web/values.yaml");
    expect(values.status).toBe("modified");
    expect(values.additions).toBe(1);
    expect(values.deletions).toBe(1);
    expect(values.hunks).toHaveLength(1);

    const lines = values.hunks[0].lines;
    expect(lines.map((l) => l.type)).toEqual(["context", "context", "del", "add", "context"]);
    expect(lines[0]).toMatchObject({ oldNo: 3, newNo: 3, text: "  repository: nginx" });
    expect(lines[2]).toMatchObject({ oldNo: 5, newNo: null, text: '  port: "eighty"' });
    expect(lines[3]).toMatchObject({ oldNo: null, newNo: 5, text: "  port: 80" });
    expect(lines[4]).toMatchObject({ oldNo: 6, newNo: 6 });

    expect(created.status).toBe("added");
    expect(created.path).toBe("charts/web/templates/new.yaml");
    // A YAML document separator inside the hunk must not be mistaken for a file header.
    expect(created.hunks[0].lines[0]).toMatchObject({ type: "add", text: "---", newNo: 1 });
    expect(created.additions).toBe(2);
  });

  it("handles removed lines that look like file headers", () => {
    const diff = `--- a/x.yaml
+++ b/x.yaml
@@ -1,2 +1,1 @@
--- 
 kind: Service
`;
    const [f] = parseUnifiedDiff(diff);
    expect(f.deletions).toBe(1);
    expect(f.hunks[0].lines[0]).toMatchObject({ type: "del", text: "-- " });
  });

  it("parses plain diff -u output with multiple files", () => {
    const diff = `--- a/one.txt
+++ b/one.txt
@@ -1 +1 @@
-a
+b
--- a/two.txt
+++ b/two.txt
@@ -1 +1 @@
-c
+d
`;
    const files = parseUnifiedDiff(diff);
    expect(files.map((f) => f.path)).toEqual(["one.txt", "two.txt"]);
  });
});
