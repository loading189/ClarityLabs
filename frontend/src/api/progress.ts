import { apiGet } from "./client";

export type AssistantProgress = {
  business_id: string;
  window_days: number;
  generated_at: string;
  health_score: { current: number; delta_window: number };
  open_signals: { current: number; delta_window: number };
  plans: { active_count: number; completed_count_window: number };
  streak_days: number;
  top_domains_open: { domain: string; count: number }[];
};

export function fetchAssistantProgress(businessId: string, windowDays = 7, signal?: AbortSignal) {
  const query = new URLSearchParams({ business_id: businessId, window_days: String(windowDays) });
  return apiGet<AssistantProgress>(`/api/assistant/progress?${query.toString()}`, { signal });
}
