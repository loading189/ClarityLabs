// frontend/src/api/ledger.ts
import { apiGet } from "./client";
import { isValidIsoDate } from "../app/filters/filters";

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

export type LedgerTraceTxn = {
  occurred_at: string;
  source_event_id: string;
  description: string;
  direction: "inflow" | "outflow";
  signed_amount: number;
  display_amount: number;
  category_name?: string | null;
  account_name?: string | null;
  counterparty_hint?: string | null;
};

export type LedgerQueryRow = {
  occurred_at: string;
  date: string;
  description: string;
  vendor: string;
  amount: number;
  category: string;
  account: string;
  balance: number;
  source_event_id: string;
  is_highlighted?: boolean;
};

export type LedgerQuerySummary = {
  start_balance: number;
  end_balance: number;
  total_in: number;
  total_out: number;
  row_count: number;
};

export type LedgerQueryResponse = {
  rows: LedgerQueryRow[];
  summary: LedgerQuerySummary;
};

export type LedgerDimensionAccount = {
  account: string;
  label: string;
  count: number;
  total: number;
};

export type LedgerDimensionVendor = {
  vendor: string;
  count: number;
  total: number;
};

function toNumber(value: unknown, fallback = 0): number {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function inferDirectionFromSignedAmount(n: number): "inflow" | "outflow" {
  return n >= 0 ? "inflow" : "outflow";
}

function normalizeLedgerLine(row: any): LedgerLine {
  const signed_amount = toNumber(row?.signed_amount ?? 0);

  const direction: "inflow" | "outflow" =
    row?.direction === "inflow" || row?.direction === "outflow"
      ? row.direction
      : inferDirectionFromSignedAmount(signed_amount);

  return {
    occurred_at: String(row?.occurred_at ?? ""),
    source_event_id: String(row?.source_event_id ?? ""),
    description: String(row?.description ?? ""),
    direction,
    signed_amount,

    display_amount: row?.display_amount != null ? toNumber(row.display_amount) : null,

    category_id: row?.category_id != null ? String(row.category_id) : null,
    category_name: row?.category_name != null ? String(row.category_name) : null,

    account_id: row?.account_id != null ? String(row.account_id) : null,
    account_name: row?.account_name != null ? String(row.account_name) : null,
    account_type: row?.account_type != null ? String(row.account_type) : null,
    account_subtype: row?.account_subtype != null ? String(row.account_subtype) : null,

    counterparty_hint: row?.counterparty_hint ?? null,
    payload: row?.payload ?? null,
    categorization: row?.categorization ?? null,
  };
}

function buildSearchParams(base?: Record<string, unknown>): URLSearchParams {
  const params = new URLSearchParams();
  if (!base) return params;
  for (const [k, v] of Object.entries(base)) {
    if (v === undefined || v === null) continue;
    params.set(k, String(v));
  }
  return params;
}

export async function fetchLedgerLines(
  businessId: string,
  query: LedgerLinesQuery,
  signal?: AbortSignal
) {
  const start = query.start_date;
  const end = query.end_date;
  if (!start || !end) {
    throw new Error("Ledger lines request requires start_date and end_date");
  }
  if (!isValidIsoDate(start) || !isValidIsoDate(end) || start > end) {
    throw new Error(`Ledger lines request has invalid date range: ${start} → ${end}`);
  }

  // backend enforces le=2000
  const limit = Math.min(Math.max(query.limit ?? 2000, 1), 2000);

  const params = buildSearchParams({
    start_date: start,
    end_date: end,
    limit,
  });

  const path = `/ledger/business/${businessId}/lines?${params.toString()}`;

  const payload = await apiGet<any>(path, { signal });
  const rows: any[] = Array.isArray(payload)
    ? payload
    : Array.isArray(payload?.rows)
      ? payload.rows
      : [];
  return rows.map(normalizeLedgerLine);
}

export async function fetchLedgerTransactions(
  businessId: string,
  params: { txn_ids?: string[]; date_start?: string; date_end?: string; limit?: number },
  signal?: AbortSignal
): Promise<LedgerTraceTxn[]> {
  const search = new URLSearchParams();
  if (params.txn_ids?.length) search.set("txn_ids", params.txn_ids.join(","));
  if (params.date_start) search.set("date_start", params.date_start);
  if (params.date_end) search.set("date_end", params.date_end);
  if (params.limit) search.set("limit", String(params.limit));

  const path = `/ledger/business/${businessId}/transactions?${search.toString()}`;
  const payload = await apiGet<any>(path, { signal });
  return Array.isArray(payload) ? payload : [];
}

export async function fetchLedgerQuery(
  businessId: string,
  query: {
    start_date?: string;
    end_date?: string;
    account?: string[];
    vendor?: string[];
    category?: string[];
    search?: string;
    direction?: "inflow" | "outflow";
    source_event_id?: string[];
    highlight_source_event_id?: string[];
    limit?: number;
    offset?: number;
  },
  signal?: AbortSignal
): Promise<LedgerQueryResponse> {
  const params = new URLSearchParams();
  params.set("business_id", businessId);
  if (query.start_date) params.set("start_date", query.start_date);
  if (query.end_date) params.set("end_date", query.end_date);
  (query.account ?? []).forEach((value) => params.append("account", value));
  (query.vendor ?? []).forEach((value) => params.append("vendor", value));
  (query.category ?? []).forEach((value) => params.append("category", value));
  if (query.search) params.set("search", query.search);
  if (query.direction) params.set("direction", query.direction);
  (query.source_event_id ?? []).forEach((value) => params.append("source_event_id", value));
  (query.highlight_source_event_id ?? []).forEach((value) =>
    params.append("highlight_source_event_id", value)
  );
  if (query.limit != null) params.set("limit", String(query.limit));
  if (query.offset != null) params.set("offset", String(query.offset));

  return apiGet<LedgerQueryResponse>(`/api/ledger?${params.toString()}`, { signal });
}

export async function fetchLedgerAccountDimensions(
  businessId: string,
  query: { start_date?: string; end_date?: string },
  signal?: AbortSignal
): Promise<LedgerDimensionAccount[]> {
  const params = new URLSearchParams({ business_id: businessId });
  if (query.start_date) params.set("start_date", query.start_date);
  if (query.end_date) params.set("end_date", query.end_date);

  return apiGet<LedgerDimensionAccount[]>(
    `/api/ledger/dimensions/accounts?${params.toString()}`,
    { signal }
  );
}

export async function fetchLedgerVendorDimensions(
  businessId: string,
  query: { start_date?: string; end_date?: string },
  signal?: AbortSignal
): Promise<LedgerDimensionVendor[]> {
  const params = new URLSearchParams({ business_id: businessId });
  if (query.start_date) params.set("start_date", query.start_date);
  if (query.end_date) params.set("end_date", query.end_date);

  return apiGet<LedgerDimensionVendor[]>(
    `/api/ledger/dimensions/vendors?${params.toString()}`,
    { signal }
  );
}
