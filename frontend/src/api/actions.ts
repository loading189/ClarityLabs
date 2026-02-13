import { apiGet, apiPost } from "./client";

export type ActionStatus = "open" | "done" | "ignored" | "snoozed";

export interface ActionItem {
  id: string;
  business_id: string;
  action_type: string;
  title: string;
  summary: string;
  priority: number;
  status: ActionStatus;
  created_at: string;
  updated_at: string;
  due_at?: string | null;
  source_signal_id?: string | null;
  evidence_json?: Record<string, any> | null;
  rationale_json?: Record<string, any> | null;
  resolution_reason?: string | null;
  resolution_note?: string | null;
  resolution_meta_json?: Record<string, any> | null;
  resolved_at?: string | null;
  assigned_to_user_id?: string | null;
  resolved_by_user_id?: string | null;
  snoozed_until?: string | null;
  idempotency_key: string;
  plan_id?: string | null;
}

export interface ActionListResponse {
  actions: ActionItem[];
  summary: Record<string, number>;
}

export interface ActionRefreshResponse extends ActionListResponse {
  created_count: number;
  updated_count: number;
  suppressed_count: number;
  suppression_reasons?: Record<string, number>;
}

export async function getActions(
  businessId: string,
  params?: { status?: ActionStatus; limit?: number; offset?: number }
): Promise<ActionListResponse> {
  const search = new URLSearchParams();
  if (params?.status) search.set("status", params.status);
  if (params?.limit) search.set("limit", String(params.limit));
  if (params?.offset) search.set("offset", String(params.offset));
  const query = search.toString();
  return apiGet(`/api/actions/${businessId}${query ? `?${query}` : ""}`);
}

export async function refreshActions(businessId: string): Promise<ActionRefreshResponse> {
  return apiPost(`/api/actions/${businessId}/refresh`);
}

export async function resolveAction(
  businessId: string,
  actionId: string,
  payload: {
    status: "done" | "ignored";
    resolution_reason?: string;
    resolution_note?: string;
    resolution_meta_json?: Record<string, any>;
  }
): Promise<ActionItem> {
  return apiPost(`/api/actions/${businessId}/${actionId}/resolve`, payload);
}

export async function snoozeAction(
  businessId: string,
  actionId: string,
  payload: { until: string; reason?: string; note?: string }
): Promise<ActionItem> {
  return apiPost(`/api/actions/${businessId}/${actionId}/snooze`, payload);
}

export type ActionTriageUser = {
  id: string;
  email: string;
  name?: string | null;
};

export type ActionTriageItem = Omit<ActionItem, "updated_at" | "idempotency_key"> & {
  business_name: string;
  assigned_to_user?: ActionTriageUser | null;
};

export type ActionTriageSummary = {
  by_status: Record<string, number>;
  by_business: Array<{ business_id: string; business_name: string; counts: Record<string, number> }>;
};

export type ActionTriageResponse = {
  actions: ActionTriageItem[];
  summary: ActionTriageSummary;
};

export type ActionStateEvent = {
  id: string;
  action_id: string;
  actor_user_id: string;
  actor_email?: string | null;
  actor_name?: string | null;
  from_status: string;
  to_status: string;
  reason?: string | null;
  note?: string | null;
  created_at: string;
};

export async function assignAction(
  businessId: string,
  actionId: string,
  payload: { assigned_to_user_id: string | null }
): Promise<ActionItem> {
  return apiPost(`/api/actions/${businessId}/${actionId}/assign`, payload);
}

export async function fetchActionTriage(
  businessId: string,
  params?: { status?: ActionStatus; assigned?: "me" | "unassigned" | "any" }
): Promise<ActionTriageResponse> {
  const search = new URLSearchParams();
  if (params?.status) search.set("status", params.status);
  if (params?.assigned) search.set("assigned", params.assigned);
  const query = search.toString();
  return apiGet(`/api/actions/${businessId}/triage${query ? `?${query}` : ""}`);
}

export async function fetchActionEvents(
  businessId: string,
  actionId: string
): Promise<ActionStateEvent[]> {
  return apiGet(`/api/actions/${businessId}/${actionId}/events`);
}
