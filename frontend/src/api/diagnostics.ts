import { apiGet } from "./client";

export type ReconcileConnection = {
  provider: string;
  status: string;
  is_enabled: boolean;
  last_sync_at?: string | null;
  last_success_at?: string | null;
  last_error_at?: string | null;
  last_error?: Record<string, any> | null;
  provider_cursor?: string | null;
  last_ingested_source_event_id?: string | null;
  last_processed_source_event_id?: string | null;
  processing_stale: boolean;
};

export type ReconcileResponse = {
  business_id: string;
  counts: {
    raw_events_total: number;
    posted_txns_total: number;
    categorized_txns_total: number;
  };
  latest_markers: {
    raw_event_occurred_at?: string | null;
    raw_event_source_event_id?: string | null;
  };
  connections: ReconcileConnection[];
};

export type IntegrationRun = {
  id: string;
  provider?: string | null;
  run_type: string;
  status: string;
  started_at: string;
  finished_at?: string | null;
  before_counts?: Record<string, any> | null;
  after_counts?: Record<string, any> | null;
  detail?: Record<string, any> | null;
};

export function getDiagnosticsReconcile(businessId: string) {
  return apiGet<ReconcileResponse>(`/diagnostics/reconcile/${businessId}`);
}

export function getIntegrationRuns(businessId: string) {
  return apiGet<IntegrationRun[]>(`/diagnostics/audit/${businessId}`);
}
