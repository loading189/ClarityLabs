import { apiGet, apiPost } from "./client";
import type { AssistantThreadMessage } from "./assistantThread";

export type DailyBriefPlaybook = {
  id: string;
  title: string;
  deep_link: string | null;
};

export type DailyBriefPriority = {
  signal_id: string;
  title: string;
  severity: string;
  status: string;
  why_now: string;
  recommended_playbooks: DailyBriefPlaybook[];
  clear_condition_summary: string;
};

export type DailyBriefOut = {
  business_id: string;
  date: string;
  generated_at: string;
  headline: string;
  summary_bullets: string[];
  priorities: DailyBriefPriority[];
  metrics: {
    health_score: number;
    delta_7d: number | null;
    open_signals_count: number;
    new_changes_count: number;
  };
  links: Record<string, string>;
};

export type DailyBriefPublishOut = {
  message: AssistantThreadMessage;
  brief: DailyBriefOut;
};

export function getDailyBrief(businessId: string, date?: string, signal?: AbortSignal) {
  const query = new URLSearchParams({ business_id: businessId });
  if (date) query.set("date", date);
  return apiGet<DailyBriefOut>(`/api/assistant/daily_brief?${query.toString()}`, { signal });
}

export function publishDailyBrief(businessId: string, date?: string) {
  const query = new URLSearchParams({ business_id: businessId });
  if (date) query.set("date", date);
  return apiPost<DailyBriefPublishOut>(`/api/assistant/daily_brief/publish?${query.toString()}`, {});
}
