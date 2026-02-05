import { apiGet, apiPost } from "./client";

export type PlanStatus = "open" | "in_progress" | "done";
export type PlanStepStatus = "todo" | "done";

export type ResolutionPlanStep = {
  step_id: string;
  title: string;
  playbook_id?: string | null;
  status: PlanStepStatus;
};

export type ResolutionPlanOutcome = {
  health_score_at_start?: number;
  health_score_at_done?: number;
  health_score_delta?: number;
  signals_total: number;
  signals_resolved_count: number;
  signals_still_open_count: number;
  summary_bullets: string[];
};

export type ResolutionPlanNote = {
  id: string;
  created_at: string;
  text: string;
  actor?: string;
};

export type ResolutionPlan = {
  plan_id: string;
  business_id: string;
  title: string;
  status: PlanStatus;
  created_at: string;
  updated_at: string;
  signal_ids: string[];
  steps: ResolutionPlanStep[];
  notes: ResolutionPlanNote[];
  completed_at?: string | null;
  outcome?: ResolutionPlanOutcome | null;
};

export function listPlans(businessId: string, signal?: AbortSignal) {
  const query = new URLSearchParams({ business_id: businessId });
  return apiGet<ResolutionPlan[]>(`/api/assistant/plans?${query.toString()}`, { signal });
}

export function createPlan(payload: { business_id: string; title?: string; signal_ids: string[] }) {
  return apiPost<ResolutionPlan>(`/api/assistant/plans`, payload);
}

export function markPlanStepDone(businessId: string, planId: string, payload: { step_id: string; actor: string; note?: string }) {
  const query = new URLSearchParams({ business_id: businessId });
  return apiPost<ResolutionPlan>(`/api/assistant/plans/${encodeURIComponent(planId)}/step_done?${query.toString()}`, payload);
}

export function addPlanNote(businessId: string, planId: string, payload: { actor: string; text: string }) {
  const query = new URLSearchParams({ business_id: businessId });
  return apiPost<ResolutionPlan>(`/api/assistant/plans/${encodeURIComponent(planId)}/note?${query.toString()}`, payload);
}

export function updatePlanStatus(businessId: string, planId: string, payload: { actor: string; status: PlanStatus }) {
  const query = new URLSearchParams({ business_id: businessId });
  return apiPost<ResolutionPlan>(`/api/assistant/plans/${encodeURIComponent(planId)}/status?${query.toString()}`, payload);
}
