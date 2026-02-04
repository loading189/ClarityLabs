import { apiGet, apiPost } from "./client";

export type MonitorCounts = {
  by_status: Record<string, number>;
  by_severity: Record<string, number>;
};

export type MonitorStatus = {
  business_id: string;
  last_pulse_at: string | null;
  newest_event_at: string | null;
  open_count: number;
  counts: MonitorCounts;
};

export type MonitorPulseResponse = {
  ran: boolean;
  last_pulse_at: string | null;
  newest_event_at: string | null;
  counts: MonitorCounts;
  touched_signal_ids: string[];
};

export function getMonitorStatus(businessId: string) {
  return apiGet<MonitorStatus>(`/monitor/status/${businessId}`);
}

export function runMonitorPulse(businessId: string) {
  return apiPost<MonitorPulseResponse>(`/sim/pulse/${businessId}`, undefined);
}
