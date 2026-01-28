// src/hooks/useTransactions.ts
import { useEffect, useState, useCallback } from "react";
import { fetchTransactions } from "../api/transactions";
import type { TransactionsResponse } from "../api/transactions";
import { logRefresh } from "../utils/refreshLog";

export function useTransactions(
  businessId: string | null,
  limit = 50,
  sourceEventIds?: string[]
) {
  const [data, setData] = useState<TransactionsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!businessId) return;
    setLoading(true);
    setErr(null);
    try {
      logRefresh("transactions", "refresh");
      const res = await fetchTransactions(businessId, limit, sourceEventIds);
      setData(res);
    } catch (e: any) {
      setErr(e?.message ?? "Failed to load transactions");
    } finally {
      setLoading(false);
    }
  }, [businessId, limit, sourceEventIds?.join(",")]); // join for stable deps

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { data, loading, err, refresh };
}
