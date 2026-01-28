import { useEffect, useState } from "react";
import { fetchMonthlyTrends } from "../api/demo";
import { logRefresh } from "../utils/refreshLog";

export function useMonthlyTrends(businessId: string | null, lookbackMonths = 12, k = 2.0) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function refresh() {
    if (!businessId) return;
    setLoading(true);
    setErr(null);
    try {
      logRefresh("trends", "refresh");
      const json = await fetchMonthlyTrends(businessId, lookbackMonths, k);
      setData(json);
    } catch (e: any) {
      setErr(e?.message ?? "Failed to load trends");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setData(null);
    if (!businessId) return;
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [businessId, lookbackMonths, k]);

  return { data, loading, err, refresh };
}
