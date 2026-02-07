import { apiGet } from "./client";

export type IntegrationConnection = {
  id: string;
  business_id: string;
  provider: string;
  status: string;
  connected_at?: string | null;
  last_sync_at?: string | null;
  last_cursor?: string | null;
  last_cursor_at?: string | null;
  last_webhook_at?: string | null;
  last_ingest_counts?: { inserted?: number; skipped?: number } | null;
  last_error?: string | null;
};

export function listIntegrationConnections(businessId: string) {
  return apiGet<IntegrationConnection[]>(`/api/integrations/${businessId}`);
}
