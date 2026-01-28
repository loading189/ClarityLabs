import { useCallback, useEffect, useState } from "react";
import { logRefresh } from "../utils/refreshLog";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

export type LedgerLine = {
  occurred_at: string;
  source_event_id: string;
  description: string;
  direction: "inflow" | "outflow";
  signed_amount: number;
  display_amount: number;

  category_id: string;
  category_name: string;

  account_id: string;
  account_name: string;
  account_type: string;
  account_subtype?: string | null;
};

export type IncomeStatement = {
  start_date: string; // YYYY-MM-DD
  end_date: string;   // YYYY-MM-DD
  revenue_total: number;
  expense_total: number;
  net_income: number;
  revenue: { name: string; amount: number }[];
  expenses: { name: string; amount: number }[];
};

export type CashFlow = {
  start_date: string;
  end_date: string;
  cash_in: number;
  cash_out: number;
  net_cash_flow: number;
};

export type BalanceSheetV1 = {
  as_of: string; // YYYY-MM-DD
  cash: number;
  assets_total: number;
  liabilities_total: number;
  equity_total: number;
};

function qs(params: Record<string, string | number | undefined | null>) {
  const sp = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v === undefined || v === null || v === "") return;
    sp.set(k, String(v));
  });
  const s = sp.toString();
  return s ? `?${s}` : "";
}

function todayISO() {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function daysAgoISO(days: number) {
  const d = new Date();
  d.setDate(d.getDate() - days);
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

export function useLedger(businessId: string, opts?: { days?: number; limit?: number }) {
  const days = opts?.days ?? 30;
  const limit = opts?.limit ?? 500;

  const [lines, setLines] = useState<LedgerLine[] | null>(null);
  const [is, setIS] = useState<IncomeStatement | null>(null);
  const [cf, setCF] = useState<CashFlow | null>(null);
  const [bs, setBS] = useState<BalanceSheetV1 | null>(null);

  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const start_date = daysAgoISO(days);
  const end_date = todayISO();
  const as_of = end_date;

  const refresh = useCallback(async () => {
    if (!businessId) return;

    setLoading(true);
    setErr(null);

    try {
      logRefresh("ledger", "refresh");
      const linesUrl =
        `${API_BASE}/ledger/business/${businessId}/lines` +
        qs({ start_date, end_date, limit });

      const isUrl =
        `${API_BASE}/ledger/business/${businessId}/income_statement` +
        qs({ start_date, end_date });

      const cfUrl =
        `${API_BASE}/ledger/business/${businessId}/cash_flow` +
        qs({ start_date, end_date });

      const bsUrl =
        `${API_BASE}/ledger/business/${businessId}/balance_sheet_v1` +
        qs({ as_of, starting_cash: 0 });

      const [linesRes, isRes, cfRes, bsRes] = await Promise.all([
        fetch(linesUrl),
        fetch(isUrl),
        fetch(cfUrl),
        fetch(bsUrl),
      ]);

      // lines is the most important; if that fails, show error.
      if (!linesRes.ok) throw new Error(`Ledger lines failed (${linesRes.status})`);
      const linesJson = (await linesRes.json()) as LedgerLine[];

      // the statements can fail if backend not wired yet; handle gracefully
      const isJson = isRes.ok ? ((await isRes.json()) as IncomeStatement) : null;
      const cfJson = cfRes.ok ? ((await cfRes.json()) as CashFlow) : null;
      const bsJson = bsRes.ok ? ((await bsRes.json()) as BalanceSheetV1) : null;

      setLines(linesJson);
      setIS(isJson);
      setCF(cfJson);
      setBS(bsJson);
    } catch (e: any) {
      setErr(e?.message ?? "Failed to load ledger");
    } finally {
      setLoading(false);
    }
  }, [businessId, start_date, end_date, limit, as_of]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return {
    start_date,
    end_date,
    as_of,
    lines,
    incomeStatement: is,
    cashFlow: cf,
    balanceSheet: bs,
    loading,
    err,
    refresh,
  };
}
