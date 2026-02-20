import { apiGet, apiPost } from "./client";

export type CaseStatus = "open" | "monitoring" | "escalated" | "resolved" | "dismissed" | "reopened";

export type CaseSummary = {
  id: string;
  business_id: string;
  domain: string;
  primary_signal_type?: string | null;
  severity: string;
  status: CaseStatus;
  risk_score_snapshot?: { score?: number; band?: string } | null;
  opened_at: string;
  last_activity_at: string;
  closed_at?: string | null;
  signal_count: number;
};

export type CaseListResponse = {
  items: CaseSummary[];
  total: number;
  page: number;
  page_size: number;
};

export type CaseDetailResponse = {
  case: CaseSummary;
  signals: Array<{ signal_id: string; signal_type?: string | null; severity?: string | null; status: string; title?: string | null; summary?: string | null }>;
  actions: Array<{ id: string; title: string; status: string; priority: number }>;
  plans: Array<{ id: string; title: string; status: string; created_at: string }>;
  ledger_anchors: Array<{ id: string; anchor_key: string; anchor_payload_json?: Record<string, unknown> | null }>;
};

export function listCases(
  businessId: string,
  params?: { status?: string; severity?: string; domain?: string; q?: string; sort?: "aging" | "severity" | "activity"; page?: number; page_size?: number },
) {
  const query = new URLSearchParams({ business_id: businessId });
  if (params?.status) query.set("status", params.status);
  if (params?.severity) query.set("severity", params.severity);
  if (params?.domain) query.set("domain", params.domain);
  if (params?.q) query.set("q", params.q);
  if (params?.sort) query.set("sort", params.sort);
  if (params?.page) query.set("page", String(params.page));
  if (params?.page_size) query.set("page_size", String(params.page_size));
  return apiGet<CaseListResponse>(`/api/cases?${query.toString()}`);
}

export function getCase(businessId: string, caseId: string) {
  const query = new URLSearchParams({ business_id: businessId });
  return apiGet<CaseDetailResponse>(`/api/cases/${encodeURIComponent(caseId)}?${query.toString()}`);
}

export function getCaseTimeline(businessId: string, caseId: string) {
  const query = new URLSearchParams({ business_id: businessId });
  return apiGet<Array<{ id: string; event_type: string; payload_json: Record<string, unknown>; created_at: string }>>(`/api/cases/${encodeURIComponent(caseId)}/timeline?${query.toString()}`);
}

export function updateCaseStatus(businessId: string, caseId: string, payload: { status: CaseStatus; reason?: string; actor?: string }) {
  const query = new URLSearchParams({ business_id: businessId });
  return apiPost(`/api/cases/${encodeURIComponent(caseId)}/status?${query.toString()}`, payload);
}
