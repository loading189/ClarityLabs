import { apiPost } from "./client";

export type PlaidLinkTokenResponse = {
  link_token: string;
  expiration?: string | null;
  request_id?: string | null;
};

export type PlaidExchangeResponse = {
  connection: {
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
    last_ingest_counts?: { inserted?: number; skipped?: number } | null;
    last_error?: string | null;
    plaid_item_id?: string | null;
    plaid_environment?: string | null;
  };
};

export type PlaidSyncResponse = {
  provider: string;
  inserted: number;
  skipped: number;
  cursor?: string | null;
  ingest_processed: any;
};

export function createPlaidLinkToken(businessId: string) {
  return apiPost<PlaidLinkTokenResponse>(`/integrations/plaid/link_token/${businessId}`);
}

export function exchangePlaidPublicToken(businessId: string, publicToken: string) {
  return apiPost<PlaidExchangeResponse>(`/integrations/plaid/exchange/${businessId}`, {
    public_token: publicToken,
  });
}

export function syncPlaid(businessId: string) {
  return apiPost<PlaidSyncResponse>(`/integrations/plaid/sync/${businessId}`);
}
