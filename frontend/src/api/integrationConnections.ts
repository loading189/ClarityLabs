import { apiGet, apiPost } from "./client";

export type IntegrationConnection = {
  id: string;
  business_id: string;
  provider: string;
  status: string;
  is_enabled: boolean;
  connected_at?: string | null;
  disconnected_at?: string | null;
  last_sync_at?: string | null;
  last_success_at?: string | null;
  last_error_at?: string | null;
  last_cursor?: string | null;
  last_cursor_at?: string | null;
  last_ingested_at?: string | null;
  last_ingested_source_event_id?: string | null;
  last_processed_at?: string | null;
  last_processed_source_event_id?: string | null;
  last_webhook_at?: string | null;
  last_ingest_counts?: { inserted?: number; skipped?: number } | null;
  last_error?: string | null;
};

export function listIntegrationConnections(businessId: string) {
  return apiGet<IntegrationConnection[]>(`/api/integrations/${businessId}`);
}

export function syncIntegration(businessId: string, provider: string) {
  return apiPost(`/api/integrations/${businessId}/${provider}/sync`);
}

export function replayIntegration(
  businessId: string,
  provider: string,
  payload: { since?: string; last_n?: number } = {}
) {
  return apiPost(`/api/integrations/${businessId}/${provider}/replay`, payload);
}

export function disableIntegration(businessId: string, provider: string) {
  return apiPost(`/api/integrations/${businessId}/${provider}/disable`);
}

export function enableIntegration(businessId: string, provider: string) {
  return apiPost(`/api/integrations/${businessId}/${provider}/enable`);
}

export function disconnectIntegration(businessId: string, provider: string) {
  return apiPost(`/api/integrations/${businessId}/${provider}/disconnect`);
}
