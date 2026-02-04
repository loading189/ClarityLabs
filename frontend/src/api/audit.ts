import { apiGet } from "./client";

export type AuditLogOut = {
  id: string;
  business_id: string;
  event_type: string;
  actor: string;
  reason?: string | null;
  source_event_id?: string | null;
  rule_id?: string | null;
  before_state?: Record<string, any> | null;
  after_state?: Record<string, any> | null;
  created_at: string;
};

export type AuditLogPage = {
  items: AuditLogOut[];
  next_cursor?: string | null;
};

export function getAuditLog(
  businessId: string,
  params?: {
    limit?: number;
    cursor?: string | null;
    event_type?: string;
    actor?: string;
    since?: string;
    until?: string;
  }
) {
  const query = new URLSearchParams();
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.cursor) query.set("cursor", params.cursor);
  if (params?.event_type) query.set("event_type", params.event_type);
  if (params?.actor) query.set("actor", params.actor);
  if (params?.since) query.set("since", params.since);
  if (params?.until) query.set("until", params.until);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<AuditLogPage>(`/audit/${businessId}${suffix}`);
}
