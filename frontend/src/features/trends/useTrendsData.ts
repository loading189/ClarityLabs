import { useEffect, useState } from "react";
import { fetchMonthlyTrends } from "../../api/demo";
import { useAppState } from "../../app/state/appState";
import type { AnalyticsPayload } from "../../types";

export type MonthlyTrendsResponse = {
  business_id: string;
  name: string;
  analytics?: AnalyticsPayload;
};

export function useTrendsData(businessId: string, lookbackMonths: number, k = 2.0) {
  const { dataVersion } = useAppState();
  const [data, setData] = useState<MonthlyTrendsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!businessId) return;
    const controller = new AbortController();
    setLoading(true);
    setErr(null);
    fetchMonthlyTrends(businessId, lookbackMonths, k, controller.signal)
      .then((payload) => setData(payload))
      .catch((e: unknown) => {
        if (e instanceof DOMException && e.name === "AbortError") return;
        if (e instanceof Error) {
          setErr(e.message);
          return;
        }
        setErr("Failed to load trends");
      })
      .finally(() => setLoading(false));

    return () => controller.abort();
  }, [businessId, dataVersion, k, lookbackMonths]);

  return { data, loading, err };
}
