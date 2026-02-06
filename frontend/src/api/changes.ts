import { apiGet } from "./client";
import type { SignalSeverity } from "./signals";

export type ChangeEvent = {
  id: string;
  occurred_at: string | null;
  type: "signal_detected" | "signal_resolved" | "signal_status_updated";
  business_id: string;
  signal_id: string;
  severity: SignalSeverity | null;
  domain: "liquidity" | "revenue" | "expense" | "timing" | "concentration" | "hygiene" | "unknown" | null;
  title: string | null;
  actor: string | null;
  reason: string | null;
  summary: string;
  links: {
    assistant: string;
    signals: string;
  };
};

export function listChanges(businessId: string, limit = 50, signal?: AbortSignal) {
  const query = new URLSearchParams({ business_id: businessId, limit: String(limit) });
  return apiGet<ChangeEvent[]>(`/api/changes?${query.toString()}`, { signal });
}
