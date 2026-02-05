import { apiGet } from "./client";

export type WorkQueueActionType = "open_explain" | "open_plan" | "start_playbook";

export type WorkQueueItem = {
  kind: "signal" | "plan";
  id: string;
  title: string;
  severity?: string | null;
  status: string;
  domain?: string | null;
  score: number;
  why_now: string;
  primary_action: {
    label: string;
    type: WorkQueueActionType;
    payload: Record<string, unknown>;
  };
  links: {
    assistant: string;
    signals?: string;
  };
};

export type WorkQueueOut = {
  business_id: string;
  generated_at: string;
  items: WorkQueueItem[];
};

export function fetchWorkQueue(businessId: string, limit = 50, signal?: AbortSignal) {
  const query = new URLSearchParams({ business_id: businessId, limit: String(limit) });
  return apiGet<WorkQueueOut>(`/api/assistant/work_queue?${query.toString()}`, { signal });
}
