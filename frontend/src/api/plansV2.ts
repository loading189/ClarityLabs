import { apiGet, apiPost } from "./client";

export type PlanStatus = "draft" | "active" | "succeeded" | "failed" | "canceled";
export type PlanCloseOutcome = "succeeded" | "failed" | "canceled";
export type PlanConditionType = "signal_resolved" | "metric_delta";
export type PlanConditionDirection = "improve" | "worsen" | "resolve";
export type PlanObservationVerdict = "no_change" | "improving" | "worsening" | "success" | "failure";

export type PlanCondition = {
  id: string;
  plan_id: string;
  type: PlanConditionType;
  signal_id?: string | null;
  metric_key?: string | null;
  baseline_window_days: number;
  evaluation_window_days: number;
  threshold?: number | null;
  direction: PlanConditionDirection;
  created_at: string;
};

export type PlanObservation = {
  id: string;
  plan_id: string;
  observed_at: string;
  evaluation_start: string;
  evaluation_end: string;
  signal_state?: string | null;
  metric_value?: number | null;
  metric_baseline?: number | null;
  metric_delta?: number | null;
  verdict: PlanObservationVerdict;
  evidence_json: Record<string, any>;
  created_at: string;
};

export type PlanStateEvent = {
  id: string;
  plan_id: string;
  actor_user_id: string;
  event_type: string;
  from_status?: string | null;
  to_status?: string | null;
  note?: string | null;
  created_at: string;
};

export type Plan = {
  id: string;
  business_id: string;
  created_by_user_id: string;
  assigned_to_user_id?: string | null;
  title: string;
  intent: string;
  status: PlanStatus;
  created_at: string;
  updated_at: string;
  activated_at?: string | null;
  closed_at?: string | null;
  source_action_id?: string | null;
  primary_signal_id?: string | null;
  idempotency_key?: string | null;
};

export type PlanDetail = {
  plan: Plan;
  conditions: PlanCondition[];
  latest_observation?: PlanObservation | null;
  observations: PlanObservation[];
  state_events: PlanStateEvent[];
};

export type PlanRefresh = {
  observation: PlanObservation;
  success_candidate: boolean;
};

export type PlanSummary = {
  id: string;
  business_id: string;
  title: string;
  status: PlanStatus;
  assigned_to_user_id?: string | null;
  latest_observation?: PlanObservation | null;
};

export function createPlan(payload: {
  business_id: string;
  title: string;
  intent: string;
  source_action_id?: string | null;
  primary_signal_id?: string | null;
  assigned_to_user_id?: string | null;
  conditions: Array<{
    type: PlanConditionType;
    signal_id?: string | null;
    metric_key?: string | null;
    baseline_window_days: number;
    evaluation_window_days: number;
    threshold?: number | null;
    direction: PlanConditionDirection;
  }>;
}) {
  const query = new URLSearchParams({ business_id: payload.business_id });
  return apiPost<PlanDetail>(`/api/plans?${query.toString()}`, payload);
}

export function listPlans(businessId: string, params?: { status?: PlanStatus; assigned_to?: string; source_action_id?: string }) {
  const query = new URLSearchParams({ business_id: businessId });
  if (params?.status) query.set("status", params.status);
  if (params?.assigned_to) query.set("assigned_to", params.assigned_to);
  if (params?.source_action_id) query.set("source_action_id", params.source_action_id);
  return apiGet<Plan[]>(`/api/plans?${query.toString()}`);
}

export function getPlanDetail(businessId: string, planId: string) {
  const query = new URLSearchParams({ business_id: businessId });
  return apiGet<PlanDetail>(`/api/plans/${encodeURIComponent(planId)}?${query.toString()}`);
}

export function activatePlan(businessId: string, planId: string) {
  const query = new URLSearchParams({ business_id: businessId });
  return apiPost<PlanDetail>(`/api/plans/${encodeURIComponent(planId)}/activate?${query.toString()}`);
}

export function assignPlan(businessId: string, planId: string, payload: { assigned_to_user_id: string | null }) {
  const query = new URLSearchParams({ business_id: businessId });
  return apiPost<PlanDetail>(`/api/plans/${encodeURIComponent(planId)}/assign?${query.toString()}`, payload);
}

export function addPlanNote(businessId: string, planId: string, payload: { note: string }) {
  const query = new URLSearchParams({ business_id: businessId });
  return apiPost<PlanDetail>(`/api/plans/${encodeURIComponent(planId)}/note?${query.toString()}`, payload);
}

export function refreshPlan(businessId: string, planId: string) {
  const query = new URLSearchParams({ business_id: businessId });
  return apiPost<PlanRefresh>(`/api/plans/${encodeURIComponent(planId)}/refresh?${query.toString()}`);
}

export function closePlan(businessId: string, planId: string, payload: { outcome: PlanCloseOutcome; note?: string | null }) {
  const query = new URLSearchParams({ business_id: businessId });
  return apiPost<PlanDetail>(`/api/plans/${encodeURIComponent(planId)}/close?${query.toString()}`, payload);
}

export function getPlanSummaries(planIds: string[]) {
  return apiPost<PlanSummary[]>("/api/plans/summary", { plan_ids: planIds });
}
