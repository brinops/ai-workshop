import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DiffView } from "./DiffView";

describe("DiffView", () => {
  it("renders file headers, counts and numbered lines", () => {
    const diff = `diff --git a/values.yaml b/values.yaml
--- a/values.yaml
+++ b/values.yaml
@@ -1,2 +1,2 @@
 service:
-  port: "eighty"
+  port: 80
`;
    render(<DiffView diff={diff} />);
    expect(screen.getByText("values.yaml")).toBeInTheDocument();
    expect(screen.getByLabelText("1 additions")).toHaveTextContent("+1");
    expect(screen.getByText("removed:")).toBeInTheDocument();
    expect(screen.getByText("  port: 80", { exact: false, normalizer: (s) => s })).toBeInTheDocument();
  });

  it("explains an empty diff", () => {
    render(<DiffView diff="" />);
    expect(screen.getByText("The diff is empty.")).toBeInTheDocument();
  });
});
