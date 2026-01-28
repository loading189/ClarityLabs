// src/api/transactions.ts
import { apiGet } from "./client";

export type NormalizedTxn = {
  id: string;
  source_event_id: string;
  occurred_at: string; // ISO
  date: string;        // YYYY-MM-DD
  description: string;
  amount: number;
  direction: "inflow" | "outflow";
  account: string;
  category: string;
  counterparty_hint?: string | null;
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
