import { GitPullRequestArrow, Terminal } from "lucide-react";
import { useHealth } from "@/hooks/queries";

export function EmptyBoard() {
  const { data: health } = useHealth();
  const checks = health?.required_checks?.length ? health.required_checks.join(", ") : "helm-validate";
  return (
    <div className="flex flex-1 items-center justify-center rounded-lg border border-dashed border-line-strong bg-sunken/40 p-10">
      <div className="max-w-xl">
        <h2 className="text-xl font-semibold tracking-tight">No pull requests are being watched yet</h2>
        <p className="mt-2 text-muted">
          A task appears here as soon as a PR is registered. The control plane then waits for the{" "}
          <code className="rounded bg-raised px-1 font-mono text-[0.9em]">{checks}</code> check and steps in only if it fails.
        </p>
        <ol className="mt-6 flex flex-col gap-4">
          <li className="flex gap-3">
            <span className="flex size-8 shrink-0 items-center justify-center rounded-md border border-line-strong bg-raised">
              <GitPullRequestArrow className="size-4 text-accent" aria-hidden />
            </span>
            <div>
              <p className="font-medium">Open a PR from Claude Code</p>
              <p className="text-sm text-muted">The project hook registers it with this control plane automatically.</p>
            </div>
          </li>
          <li className="flex gap-3">
            <span className="flex size-8 shrink-0 items-center justify-center rounded-md border border-line-strong bg-raised">
              <Terminal className="size-4 text-accent" aria-hidden />
            </span>
            <div>
              <p className="font-medium">Or prepare a workshop scenario</p>
              <pre className="mt-1.5 inline-block rounded-md border border-line bg-panel px-3 py-1.5 font-mono text-sm">just scenario A</pre>
              <p className="mt-1.5 text-sm text-muted">
                It pushes a branch with a broken chart and prints the <code className="font-mono">gh pr create</code> command to run
                from Claude Code.
              </p>
            </div>
          </li>
        </ol>
      </div>
    </div>
  );
}
