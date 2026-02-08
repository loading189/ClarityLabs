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
  resolved_at?: string | null;
  snoozed_until?: string | null;
  idempotency_key: string;
}

export interface ActionListResponse {
  actions: ActionItem[];
  summary: Record<string, number>;
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

export async function refreshActions(businessId: string): Promise<ActionListResponse> {
  return apiPost(`/api/actions/${businessId}/refresh`);
}

export async function resolveAction(
  businessId: string,
  actionId: string,
  payload: { status: "done" | "ignored"; resolution_reason?: string }
): Promise<ActionItem> {
  return apiPost(`/api/actions/${businessId}/${actionId}/resolve`, payload);
}

export async function snoozeAction(
  businessId: string,
  actionId: string,
  payload: { until: string; reason?: string }
): Promise<ActionItem> {
  return apiPost(`/api/actions/${businessId}/${actionId}/snooze`, payload);
}
