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
