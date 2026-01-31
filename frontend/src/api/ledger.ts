// frontend/src/api/ledger.ts
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

  // these may not exist from backend yet; keep optional for UI
  counterparty_hint?: string | null;
  payload?: Record<string, unknown> | null;
  categorization?: LedgerCategorization | null;
};

export type LedgerLinesQuery = {
  start_date: string;
  end_date: string;
  limit?: number;
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

  // ✅ IMPORTANT: backend enforces le=2000
  const limit = Math.min(Math.max(query.limit ?? 2000, 1), 2000);

  const params = new URLSearchParams();
  params.set("start_date", start);
  params.set("end_date", end);
  params.set("limit", String(limit));

  const url = `/ledger/business/${businessId}/lines?${params.toString()}`;

  if (import.meta.env.DEV) console.info("[ledger] lines url", url);

  const res = await apiGet<any>(url, { signal });
  const rows: any[] = Array.isArray(res) ? res : Array.isArray(res?.rows) ? res.rows : [];
  return rows.map(normalizeLedgerLine);
}
