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

export function getAuditLog(businessId: string, limit = 100) {
  return apiGet<AuditLogOut[]>(`/audit/${businessId}?limit=${limit}`);
}
