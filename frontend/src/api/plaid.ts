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

export type EnsureDynamicItemResponse = {
  business_id: string;
  provider: string;
  item_id: string;
  status: string;
};

export type PlaidPumpResponse = {
  business_id: string;
  date_range: { start_date: string; end_date: string };
  seed_key: string;
  txns_requested: number;
  txns_created: number;
  sync?: { new: number; updated: number; removed: number; cursor?: string | null } | null;
  pipeline?: { ledger_rows: number; signals_open_count: number } | null;
  actions?: {
    created_count: number;
    updated_count: number;
    suppressed_count: number;
    suppression_reasons: Record<string, number>;
  } | null;
};

export function ensureDynamicPlaidItem(businessId: string, forceRecreate = false) {
  return apiPost<EnsureDynamicItemResponse>(`/api/dev/plaid/${businessId}/ensure_dynamic_item`, {
    force_recreate: forceRecreate,
  });
}

export function pumpPlaidTransactions(
  businessId: string,
  payload: {
    start_date: string;
    end_date: string;
    daily_txn_count: number;
    profile: "retail" | "services" | "ecom" | "mixed";
    run_sync?: boolean;
    run_pipeline?: boolean;
    refresh_actions?: boolean;
  },
) {
  return apiPost<PlaidPumpResponse>(`/api/dev/plaid/${businessId}/pump_transactions`, payload);
}
