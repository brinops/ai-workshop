/**
 * Typed client for the control-plane REST API. Types mirror backend/app/api/schemas.py.
 * Timestamps are ISO-8601 strings in UTC (suffix "Z").
 */

export type TaskState =
  | "NEW"
  | "WAITING_CI"
  | "ANALYZING"
  | "TODO"
  | "IN_PROGRESS"
  | "VALIDATING"
  | "DONE"
  | "NEEDS_REVIEW"
  | "FAILED";

export type ColumnId = "NEW" | "TODO" | "IN_PROGRESS" | "DONE";

export type Classification =
  | "SYNTAX_ERROR"
  | "SCHEMA_VIOLATION"
  | "LOGICAL_CONFIGURATION_ERROR"
  | "NON_REMEDIABLE"
  | "UNKNOWN";

export type CIOverall = "pending" | "success" | "failure" | "cancelled" | "skipped";
export type PendingAction = "analyze" | "remediate" | "push";

export type ActionName =
  | "analyze"
  | "start_remediation"
  | "approve_push"
  | "retry"
  | "pause"
  | "resume"
  | "cancel"
  | "mark_review";

export interface TaskCard {
  id: number;
  repo: string;
  pr_number: number;
  pr_url: string;
  title: string;
  author: string | null;
  head_branch: string;
  base_branch: string;
  head_sha: string;
  expected_sha: string;
  source: string;
  /** control-plane.yaml route (failed CI check name) handling this task. */
  route: string | null;
  state: TaskState;
  column: ColumnId;
  pending_action: PendingAction | string | null;
  paused: boolean;
  cancel_requested: boolean;
  resolution: string | null;
  classification: Classification | string | null;
  confidence: number | null;
  root_cause: string | null;
  ci_status: CIOverall | string | null;
  ci_checked_at: string | null;
  ci_waiting_since: string | null;
  ci_next_check_at: string | null;
  attempt: number;
  max_attempts: number;
  activity: string | null;
  agent_running: boolean;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

export type EventLevel = "info" | "success" | "warning" | "error" | string;

export interface EventOut {
  id: number;
  task_id: number | null;
  ts: string;
  type: string;
  level: EventLevel;
  message: string;
  data: Record<string, unknown> | null;
}

export interface CommentOut {
  id: number;
  ts: string;
  author: string;
  kind: "diagnosis" | "remediation" | "note" | string;
  body_md: string;
  data: Record<string, unknown> | null;
}

export interface AgentRunOut {
  id: number;
  kind: "analysis" | "remediation" | string;
  attempt: number;
  status: string;
  model: string | null;
  session_id: string | null;
  exit_code: number | null;
  cost_usd: number | null;
  num_turns: number | null;
  error: string | null;
  started_at: string;
  finished_at: string | null;
  output: Record<string, unknown> | null;
}

export type LogKind = "system" | "text" | "tool_use" | "tool_result" | "result" | "stderr";

export interface LogLineOut {
  id: number;
  run_id: number;
  task_id: number;
  ts: string;
  kind: LogKind | string;
  text: string;
  /** Full tool input / output (present when the summary in `text` is abridged). */
  detail: string | null;
}

/** Report produced by a route's validator (e.g. .claude/skills/k8s-failure-analysis/scripts/validate.py --format json). */
export interface ValidatorFinding {
  category: string;
  check: string;
  message: string;
  chart: string;
  file?: string | null;
  line?: number | null;
  resource?: string | null;
}

export interface ValidatorStage {
  name: string;
  status: "passed" | "failed" | "skipped" | "error" | string;
  detail?: string;
}

export interface ValidatorChart {
  chart: string;
  stages: ValidatorStage[];
  findings: ValidatorFinding[];
}

export interface ValidationReport {
  valid?: boolean;
  charts?: ValidatorChart[];
  exit_code?: number;
  tool_error?: string | null;
}

export interface ChangedFile {
  path: string;
  status: string;
  added: number;
  removed: number;
}

export interface RemediationOut {
  id: number;
  attempt: number;
  run_id: number | null;
  base_sha: string;
  summary: string;
  diff: string;
  files: ChangedFile[];
  scope_ok: boolean;
  scope_violations: string[];
  validation_passed: boolean;
  validation: ValidationReport | null;
  commit_sha: string | null;
  push_status: string;
  push_error: string | null;
  pushed_at: string | null;
  created_at: string;
}

export interface ValidationRunOut {
  id: number;
  sha: string;
  purpose: string;
  valid: boolean;
  exit_code: number;
  report: ValidationReport | null;
  ts: string;
}

export interface CICheck {
  name: string;
  verdict: "success" | "failure" | "pending" | "missing" | "cancelled" | "skipped" | string;
  id?: number;
  status?: string;
  conclusion?: string | null;
  html_url?: string | null;
  details_url?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  app_slug?: string | null;
}

export interface CISnapshotOut {
  id: number;
  sha: string;
  overall: CIOverall | string;
  checks: CICheck[];
  ts: string;
}

export interface NotificationOut {
  id: number;
  channel: string;
  kind: string;
  status: "sent" | "failed" | "skipped" | "queued" | string;
  error: string | null;
  preview: string | null;
  ts: string;
}

export interface TaskDetail {
  task: TaskCard;
  actions: ActionName[];
  events: EventOut[];
  comments: CommentOut[];
  runs: AgentRunOut[];
  remediations: RemediationOut[];
  validations: ValidationRunOut[];
  ci: CISnapshotOut[];
  notifications: NotificationOut[];
}

export interface Board {
  columns: Record<ColumnId, TaskCard[]>;
  counts: Record<ColumnId, number>;
  state_counts: Record<TaskState, number>;
}

export interface Automation {
  auto_analyze: boolean;
  auto_remediate: boolean;
  auto_push: boolean;
}

export interface ActionOut {
  ok: boolean;
  message: string;
  task: TaskCard;
}

export interface HealthComponent {
  ok: boolean;
  detail: string;
}

export interface Health {
  ok: boolean;
  components: Record<string, HealthComponent>;
  agents_running: number;
  required_checks: string[];
  allowed_paths: string[];
  model: string;
  max_attempts: number;
}

/* ----------------------------------------------------------- diagnosis comment data */

export interface AnalysisOutput {
  classification: string;
  root_cause: string;
  affected_files?: { path: string; line?: number | null; reason?: string }[];
  evidence?: { source: string; detail: string }[];
  proposed_fix?: {
    summary?: string;
    steps?: string[];
    changes?: { file: string; description: string }[];
  };
  confidence?: number;
  auto_remediation_appropriate?: boolean;
  auto_remediation_rationale?: string;
  markdown?: string;
}

export interface Reconciled {
  classification: string;
  llm_classification: string | null;
  deterministic_classification: string | null;
  agreement: boolean;
  remediable: boolean;
  decision_reason: string;
  out_of_scope_files?: string[];
}

export interface DiagnosisData {
  analysis?: AnalysisOutput;
  reconciled?: Reconciled;
  findings?: ValidatorFinding[];
  findings_source?: "ci" | "local" | string;
  sha?: string;
  run_id?: number;
}

/* ----------------------------------------------------------------- HTTP client */

export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      ...init,
      headers: { Accept: "application/json", ...(init?.body ? { "Content-Type": "application/json" } : {}), ...init?.headers },
    });
  } catch {
    throw new ApiError(0, "Cannot reach the control-plane backend");
  }
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") message = body.detail;
      else if (body.detail) message = JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, message);
  }
  return (await res.json()) as T;
}

export const api = {
  board: () => request<Board>("/api/board"),
  task: (id: number) => request<TaskDetail>(`/api/tasks/${id}`),
  runLogs: (taskId: number, runId: number, after = 0) =>
    request<LogLineOut[]>(`/api/tasks/${taskId}/runs/${runId}/logs?after=${after}`),
  action: (taskId: number, action: ActionName) =>
    request<ActionOut>(`/api/tasks/${taskId}/actions/${action}`, { method: "POST" }),
  automation: () => request<Automation>("/api/settings/automation"),
  setAutomation: (patch: Partial<Automation>) =>
    request<Automation>("/api/settings/automation", { method: "PUT", body: JSON.stringify(patch) }),
  health: () => request<Health>("/api/health"),
  events: (limit = 50) => request<EventOut[]>(`/api/events?limit=${limit}`),
  config: () => request<ControlPlaneConfig>("/api/config"),
};

export const STREAM_URL = "/api/stream";

/** One route of control-plane.yaml: failed check → skill, agent, validator, editable paths. */
export interface Route {
  check: string;
  analysis_skill: string;
  remediation_agent: string;
  validator: string;
  allowed_paths: string[];
  max_changed_lines: number;
  max_attempts: number;
}

export interface ControlPlaneConfig {
  path: string;
  repositories: { repo: string; protected_branches: string[]; routes: Route[] }[];
}
