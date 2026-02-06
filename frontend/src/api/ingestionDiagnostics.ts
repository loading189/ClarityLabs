import { apiGet } from "./client";

export type ProcessingError = {
  source_event_id: string;
  provider: string;
  error_code?: string | null;
  error_detail?: string | null;
  updated_at?: string | null;
};

export type IngestionConnectionStatus = {
  provider: string;
  status: string;
  last_sync_at?: string | null;
  last_cursor?: string | null;
  last_cursor_at?: string | null;
  last_webhook_at?: string | null;
  last_ingest_counts?: Record<string, number> | null;
  last_error?: string | null;
};

export type IngestionDiagnostics = {
  status_counts: Record<string, number>;
  errors: ProcessingError[];
  connections: IngestionConnectionStatus[];
  monitor_status: {
    stale?: boolean;
    last_pulse_at?: string | null;
    newest_event_at?: string | null;
    gating_reason?: string | null;
  };
};

export function fetchIngestionDiagnostics(businessId: string, signal?: AbortSignal) {
  return apiGet<IngestionDiagnostics>(`/api/diagnostics/ingestion/${businessId}`, { signal });
}
