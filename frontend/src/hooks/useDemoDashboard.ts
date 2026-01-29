import { useCallback, useEffect, useRef, useState } from "react";
import { fetchBusinessDashboard } from "../api/demo";
import type { DashboardDetail } from "../types";

export function useDemoDashboard(businessId: string) {
  const [data, setData] = useState<DashboardDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const seqRef = useRef(0);

  const load = useCallback(async () => {
    if (!businessId) return;
    const seq = (seqRef.current += 1);
    setLoading(true);
    setErr(null);
    try {
      const payload = await fetchBusinessDashboard(businessId);
      if (seq !== seqRef.current) return;
      setData(payload);
    } catch (e: any) {
      if (seq !== seqRef.current) return;
      setErr(e?.message ?? "Failed to load dashboard");
    } finally {
      if (seq === seqRef.current) {
        setLoading(false);
      }
    }
  }, [businessId]);

  useEffect(() => {
    if (!businessId) return;
    load();
  }, [businessId, load]);

  return { data, loading, err, refresh: load };
}
