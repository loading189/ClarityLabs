import { apiGet, apiPost } from "./client";

export type MonitorCounts = {
  by_status: Record<string, number>;
  by_severity: Record<string, number>;
};

export type MonitorStatus = {
  business_id: string;
  last_pulse_at: string | null;
  newest_event_at: string | null;
  newest_event_source_event_id: string | null;
  open_count: number;
  counts: MonitorCounts;
  gated: boolean;
  gating_reason: string | null;
  gating_reason_code?: string | null;
  stale?: boolean;
  stale_reason?: string | null;
};

export type MonitorPulseResponse = {
  ran: boolean;
  last_pulse_at: string | null;
  newest_event_at: string | null;
  newest_event_source_event_id?: string | null;
  counts: MonitorCounts;
  touched_signal_ids: string[];
};

export function getMonitorStatus(businessId: string) {
  return apiGet<MonitorStatus>(`/monitor/status/${businessId}`);
}

export function runMonitorPulse(businessId: string, options?: { force?: boolean }) {
  const query = options?.force ? "?force=true" : "";
  return apiPost<MonitorPulseResponse>(`/monitor/pulse/${businessId}${query}`, undefined);
}
