import { apiGet, apiPost } from "./client";

export type WorkItemStatus = "open" | "snoozed" | "completed";

export type WorkItem = {
  id: string;
  case_id: string;
  business_id: string;
  type: string;
  priority: number;
  status: WorkItemStatus;
  due_at: string | null;
  snoozed_until: string | null;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
  idempotency_key: string;
  case_severity: string;
  case_domain: string;
  assigned_to: string | null;
};

export function listWorkItems(
  businessId: string,
  params?: {
    status?: WorkItemStatus;
    priority_gte?: number;
    due_before?: string;
    assigned_only?: boolean;
    case_severity_gte?: string;
    sort?: "priority" | "due_at" | "created_at";
  },
) {
  const query = new URLSearchParams({ business_id: businessId });
  if (params?.status) query.set("status", params.status);
  if (params?.priority_gte !== undefined) query.set("priority_gte", String(params.priority_gte));
  if (params?.due_before) query.set("due_before", params.due_before);
  if (params?.assigned_only !== undefined) query.set("assigned_only", String(params.assigned_only));
  if (params?.case_severity_gte) query.set("case_severity_gte", params.case_severity_gte);
  if (params?.sort) query.set("sort", params.sort);
  return apiGet<{ items: WorkItem[]; total: number }>(`/api/work?${query.toString()}`);
}

export function completeWorkItem(businessId: string, workItemId: string) {
  return apiPost(`/api/work/${encodeURIComponent(workItemId)}/complete?business_id=${encodeURIComponent(businessId)}`, {});
}

export function snoozeWorkItem(businessId: string, workItemId: string, snoozedUntil: string) {
  return apiPost(`/api/work/${encodeURIComponent(workItemId)}/snooze?business_id=${encodeURIComponent(businessId)}`, { snoozed_until: snoozedUntil });
}
