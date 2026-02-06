// src/api/transactions.ts
import { apiGet } from "./client";

export type NormalizedTxn = {
  id: string;
  source_event_id?: string | null;
  occurred_at?: string | null; // ISO
  date?: string | null;        // YYYY-MM-DD
  description?: string | null;
  amount: number;
  direction: "inflow" | "outflow";
  account?: string | null;
  category?: string | null;
  counterparty_hint?: string | null;
  merchant_key?: string | null;
  suggested_system_key?: string | null;
  suggested_category_id?: string | null;
  suggested_category_name?: string | null;
  suggestion_source?: string | null;
  confidence?: number | null;
  reason?: string | null;
};

export type TransactionsResponse = {
  business_id: string;
  name?: string;
  as_of: string;
  last_event_occurred_at?: string | null;
  count: number;
  transactions: NormalizedTxn[];
};

export type TransactionDetail = {
  business_id: string;
  source_event_id: string;
  raw_event: {
    source: string;
    source_event_id: string;
    payload: Record<string, any>;
    occurred_at: string;
    created_at: string;
    processed_at?: string | null;
  };
  normalized_txn: {
    source_event_id: string;
    occurred_at: string;
    date: string;
    description: string;
    amount: number;
    direction: "inflow" | "outflow";
    account: string;
    category_hint: string;
    counterparty_hint?: string | null;
    merchant_key?: string | null;
  };
  vendor_normalization: {
    canonical_name: string;
    source: string;
  };
  categorization?: {
    category_id: string;
    category_name: string;
    system_key?: string | null;
    account_id: string;
    account_name: string;
    source: string;
    confidence: number;
    note?: string | null;
    rule_id?: string | null;
    created_at: string;
  } | null;
  processing_assumptions: Array<{ field: string; detail: string }>;
  ledger_context?: {
    row: {
      source_event_id: string;
      occurred_at: string;
      date: string;
      description: string;
      vendor: string;
      amount: number;
      category: string;
      account: string;
      balance: number;
    };
    balance: number;
    running_total_in: number;
    running_total_out: number;
  } | null;
  audit_history: Array<{
    id: string;
    event_type: string;
    actor: string;
    reason?: string | null;
    before_state?: Record<string, any> | null;
    after_state?: Record<string, any> | null;
    rule_id?: string | null;
    created_at: string;
  }>;
  related_signals: Array<{
    signal_id: string;
    title?: string | null;
    severity?: string | null;
    status?: string | null;
    domain?: string | null;
    updated_at?: string | null;
    matched_on?: string | null;
    window?: Record<string, any> | null;
    facts?: Record<string, any> | null;
  }>;
};

export async function fetchTransactions(
  businessId: string,
  limit = 50,
  sourceEventIds?: string[],
  category?: string,
  direction?: "inflow" | "outflow"
): Promise<TransactionsResponse> {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  if (sourceEventIds?.length) params.set("source_event_ids", sourceEventIds.join(","));
  if (category) params.set("category", category);
  if (direction) params.set("direction", direction);

  return apiGet(`/demo/transactions/${businessId}?${params.toString()}`);
}

export async function fetchTransactionDetail(
  businessId: string,
  sourceEventId: string
): Promise<TransactionDetail> {
  return apiGet(`/api/transactions/${businessId}/${encodeURIComponent(sourceEventId)}`);
}
