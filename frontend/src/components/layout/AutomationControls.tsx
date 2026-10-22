import { ShieldCheck, Zap } from "lucide-react";
import { useId } from "react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/components/ui/toast";
import { useAutomation } from "@/hooks/queries";
import { cn } from "@/lib/utils";
import type { Automation } from "@/services/api";

const ITEMS: { key: keyof Automation; label: string; on: string; off: string }[] = [
  { key: "auto_analyze", label: "Auto analyze", on: "Diagnoses failed CI immediately", off: "Waits for “Analyze now”" },
  { key: "auto_remediate", label: "Auto remediate", on: "Fixes remediable failures", off: "Waits for “Start remediation”" },
  { key: "auto_push", label: "Auto push", on: "Pushes validated fixes", off: "Approval required before pushing" },
];

function Toggle({
  item,
  checked,
  disabled,
  onChange,
  compact,
}: {
  item: (typeof ITEMS)[number];
  checked: boolean | undefined;
  disabled: boolean;
  onChange: (v: boolean) => void;
  compact: boolean;
}) {
  const id = useId();
  const needsApproval = item.key === "auto_push" && checked === false;
  return (
    <div
      className={cn(
        "flex items-center gap-3 rounded-md border px-3 py-2 transition-colors",
        needsApproval ? "border-warn/40 bg-warn/[0.06]" : "border-line bg-panel",
      )}
    >
      <Switch id={id} checked={checked ?? false} disabled={disabled || checked === undefined} onCheckedChange={onChange} />
      <label htmlFor={id} className="flex cursor-pointer flex-col leading-tight">
        <span className="text-sm font-medium">
          {item.label} <span className={cn("ml-1 text-xs", checked ? "text-ok" : "text-faint")}>{checked === undefined ? "…" : checked ? "On" : "Off"}</span>
        </span>
        {!compact && (
          <span className={cn("text-xs", needsApproval ? "text-warn" : "text-muted")}>
            {checked === undefined ? "Loading…" : checked ? item.on : item.off}
          </span>
        )}
      </label>
    </div>
  );
}

export function AutomationControls({ compact = false }: { compact?: boolean }) {
  const { data, update, updating, isError } = useAutomation();
  const { toast } = useToast();

  const apply = (patch: Partial<Automation>, title: string) =>
    update(patch, {
      onSuccess: () => toast({ tone: "success", title }),
      onError: (e) => toast({ tone: "error", title: "Couldn't save automation settings", description: (e as Error).message }),
    });

  const isAutonomous = data?.auto_analyze && data.auto_remediate && data.auto_push;
  const isSafe = data?.auto_analyze && data.auto_remediate && !data.auto_push;

  return (
    <section aria-label="Automation settings" className="flex flex-wrap items-center gap-2">
      {ITEMS.map((item) => (
        <Toggle
          key={item.key}
          item={item}
          compact={compact}
          checked={data?.[item.key]}
          disabled={updating || isError}
          onChange={(v) => apply({ [item.key]: v }, `${item.label} turned ${v ? "on" : "off"}`)}
        />
      ))}
      <div className="ml-auto flex items-center gap-2">
        <span className="hidden text-xs text-faint 2xl:inline">Presets</span>
        <Button
          variant={isSafe ? "primary" : "default"}
          aria-pressed={Boolean(isSafe)}
          disabled={updating || !data}
          onClick={() => apply({ auto_analyze: true, auto_remediate: true, auto_push: false }, "Safe preset applied — pushes need approval")}
        >
          <ShieldCheck /> Safe
        </Button>
        <Button
          variant={isAutonomous ? "primary" : "default"}
          aria-pressed={Boolean(isAutonomous)}
          disabled={updating || !data}
          onClick={() => apply({ auto_analyze: true, auto_remediate: true, auto_push: true }, "Autonomous demo preset applied")}
        >
          <Zap /> Autonomous demo
        </Button>
      </div>
    </section>
  );
}
