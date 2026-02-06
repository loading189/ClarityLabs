import { apiGet, apiPost } from "./client";

export type AssistantIntegrationStatus = {
  provider: string;
  status: string;
  last_sync_at?: string | null;
  last_error?: string | null;
};

export type AssistantSummary = {
  business_id: string;
  integrations: AssistantIntegrationStatus[];
  monitor_status: {
    stale: boolean;
    gated: boolean;
    gating_reason?: string | null;
    stale_reason?: string | null;
    last_pulse_at?: string | null;
  };
  open_signals: number;
  uncategorized_count: number;
  audit_events: Array<{
    id: string;
    event_type: string;
    actor: string;
    reason?: string | null;
    created_at: string;
  }>;
  top_vendors: Array<{ vendor: string; total_spend: number }>;
};

export type AssistantActionResponse = {
  ok: boolean;
  navigation_hint?: { path: string };
  result?: any;
};

export function fetchAssistantSummary(businessId: string, signal?: AbortSignal) {
  return apiGet<AssistantSummary>(`/api/assistant/summary/${businessId}`, { signal });
}

export function postAssistantAction(businessId: string, action_type: string, payload?: Record<string, unknown>) {
  return apiPost<AssistantActionResponse>(`/api/assistant/action/${businessId}`, { action_type, payload });
}
