import { apiGet, apiPost } from "./client";

export type AssistantAuthor = "system" | "assistant" | "user";
export type AssistantKind = "summary" | "changes" | "priority" | "explain" | "action_result" | "note" | "playbook_started" | "daily_brief" | "plan" | "plan_created" | "plan_step_done" | "plan_note_added" | "plan_status_updated";

export type AssistantThreadMessage = {
  id: string;
  business_id: string;
  created_at: string;
  author: AssistantAuthor;
  kind: AssistantKind;
  signal_id: string | null;
  audit_id: string | null;
  content_json: Record<string, unknown>;
};

export type AssistantThreadMessageIn = {
  author: AssistantAuthor;
  kind: AssistantKind;
  signal_id?: string | null;
  audit_id?: string | null;
  content_json: Record<string, unknown>;
};

export function fetchAssistantThread(businessId: string, limit = 200, signal?: AbortSignal) {
  const query = new URLSearchParams({ business_id: businessId, limit: String(limit) });
  return apiGet<AssistantThreadMessage[]>(`/api/assistant/thread?${query.toString()}`, { signal });
}

export function postAssistantMessage(businessId: string, message: AssistantThreadMessageIn) {
  const query = new URLSearchParams({ business_id: businessId });
  return apiPost<AssistantThreadMessage>(`/api/assistant/thread?${query.toString()}`, message);
}
