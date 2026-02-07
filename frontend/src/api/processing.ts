import { apiPost } from "./client";

export type ReprocessRequest = {
  mode?: "from_last_cursor" | "from_beginning" | "from_source_event_id";
  from_source_event_id?: string;
};

export function reprocessPipeline(businessId: string, payload: ReprocessRequest = {}) {
  return apiPost(`/processing/reprocess/${businessId}`, payload);
}
