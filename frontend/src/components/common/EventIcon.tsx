import {
  Activity,
  ArrowRightLeft,
  Bell,
  Bot,
  CheckCheck,
  CircleDot,
  Cog,
  GitCommitHorizontal,
  GitPullRequestArrow,
  Hand,
  Pause,
  Play,
  RefreshCcw,
  Rocket,
  Scale,
  ShieldCheck,
  Siren,
  Sparkles,
  ThumbsUp,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import { levelColor, levelRing } from "@/lib/events";
import { cn } from "@/lib/utils";

const ICONS: Record<string, LucideIcon> = {
  registered: GitPullRequestArrow,
  state_changed: ArrowRightLeft,
  ci_status: Workflow,
  ci_poll_error: Siren,
  agent_started: Bot,
  agent_finished: Sparkles,
  comment_added: CircleDot,
  local_validation: ShieldCheck,
  fix_committed: GitCommitHorizontal,
  pushed: Rocket,
  awaiting_approval: Hand,
  push_approved: ThumbsUp,
  notification: Bell,
  recovered: RefreshCcw,
  paused: Pause,
  resumed: Play,
  classification_overridden: Scale,
  analysis_retry: RefreshCcw,
  new_commit: GitCommitHorizontal,
  retargeted: GitCommitHorizontal,
  settings_changed: Cog,
  worker_started: Activity,
  worker_stopped: Activity,
  stage_aborted: Siren,
  fix_regenerate: RefreshCcw,
};

export function EventIcon({ type, level, className }: { type: string; level: string; className?: string }) {
  const Icon = ICONS[type] ?? (level === "success" ? CheckCheck : CircleDot);
  return (
    <span
      className={cn("inline-flex size-6 shrink-0 items-center justify-center rounded-full border", levelRing(level), className)}
      aria-hidden
    >
      <Icon className={cn("size-3.5", levelColor(level))} />
    </span>
  );
}
