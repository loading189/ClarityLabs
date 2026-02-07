import { apiGet } from "./client";

export type ReconcileConnection = {
  provider: string;
  status: string;
  provider_cursor?: string | null;
  provider_cursor_at?: string | null;
  last_ingested_at?: string | null;
  last_ingested_source_event_id?: string | null;
  last_processed_at?: string | null;
  last_processed_source_event_id?: string | null;
  mismatch_flags: {
    processing_stale: boolean;
    cursor_missing_timestamp: boolean;
  };
};

export type IngestionReconcile = {
  counts: {
    raw_events: number;
    posted_transactions: number;
    categorized_transactions: number;
  };
  latest_markers: {
    raw_event_occurred_at?: string | null;
    raw_event_source_event_id?: string | null;
    connections: ReconcileConnection[];
  };
};

export function fetchIngestionReconcile(businessId: string, signal?: AbortSignal) {
  return apiGet<IngestionReconcile>(`/api/diagnostics/reconcile/${businessId}`, { signal });
}
