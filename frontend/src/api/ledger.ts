import { apiGet } from "./client";

export type LedgerCategorization = {
  confidence?: number | null;
  reason?: string | null;
  source?: string | null;
  status?: string | null;
};

export type LedgerLine = {
  occurred_at: string;
  source_event_id: string;
  description: string;
  direction: "inflow" | "outflow";
  signed_amount: number;
  display_amount?: number | null;
  category_id?: string | null;
  category_name?: string | null;
  account_id?: string | null;
  account_name?: string | null;
  account_type?: string | null;
  account_subtype?: string | null;
  counterparty_hint?: string | null;
  payload?: Record<string, unknown> | null;
  categorization?: LedgerCategorization | null;
};

export type LedgerLinesQuery = {
  start_date: string;
  end_date: string;
  limit?: number;
};

export function fetchLedgerLines(
  businessId: string,
  query: LedgerLinesQuery,
  signal?: AbortSignal
) {
  const params = new URLSearchParams();
  params.set("start_date", query.start_date);
  params.set("end_date", query.end_date);
  if (query.limit != null) params.set("limit", String(query.limit));
  if (!params.get("start_date") || !params.get("end_date")) {
    throw new Error("Ledger lines request requires start_date and end_date");
  }
  const url = `/ledger/business/${businessId}/lines?${params.toString()}`;
  if (import.meta.env.DEV) {
    console.info(`[ledger] lines url`, url);
  }
  return apiGet<LedgerLine[]>(url, { signal });
}
