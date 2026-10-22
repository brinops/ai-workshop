import type { CommentOut, DiagnosisData, RemediationOut, TaskDetail } from "@/services/api";

export function latestDiagnosis(detail: TaskDetail): { comment: CommentOut; data: DiagnosisData } | null {
  for (let i = detail.comments.length - 1; i >= 0; i--) {
    const c = detail.comments[i];
    if (c.kind === "diagnosis") return { comment: c, data: (c.data ?? {}) as DiagnosisData };
  }
  return null;
}

export function latestRemediation(detail: TaskDetail): RemediationOut | null {
  return detail.remediations.length ? detail.remediations[detail.remediations.length - 1] : null;
}

/** True when deterministic validator evidence overrode the LLM's classification. */
export function isOverridden(data: DiagnosisData | null | undefined): boolean {
  const r = data?.reconciled;
  return Boolean(r && r.deterministic_classification && !r.agreement);
}
