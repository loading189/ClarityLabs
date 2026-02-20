import { apiGet, apiPost } from "./client";

export type TickResult = {
  business_id: string;
  bucket: string;
  cases_processed: number;
  cases_recompute_changed: number;
  cases_recompute_applied: number;
  work_items_created: number;
  work_items_updated: number;
  work_items_auto_resolved: number;
  work_items_unchanged: number;
  errors: Array<{ case_id?: string; message: string }>;
  started_at: string;
  finished_at: string;
};

export type LastTickResponse = {
  business_id: string;
  bucket: string;
  finished_at: string;
  result_summary: {
    cases_processed: number;
    cases_recompute_changed: number;
    cases_recompute_applied: number;
    work_items_created: number;
    work_items_updated: number;
    work_items_auto_resolved: number;
    work_items_unchanged: number;
  };
} | null;

export function tickSystem(params: {
  business_id: string;
  apply_recompute?: boolean;
  materialize_work?: boolean;
  limit_cases?: number;
}) {
  return apiPost<TickResult>("/api/system/tick", params);
}

export function getLastTick(businessId: string) {
  return apiGet<LastTickResponse>(`/api/system/last-tick?business_id=${encodeURIComponent(businessId)}`);
}
