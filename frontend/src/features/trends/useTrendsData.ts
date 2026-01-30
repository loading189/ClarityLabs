import { useEffect, useState } from "react";
import { fetchMonthlyTrends } from "../../api/demo";

export type TrendRow = {
  month: string;
  inflow: number;
  outflow: number;
  net: number;
  cash_end: number;
};

export type MetricSeriesRow = {
  month: string;
  inflow: number;
  outflow: number;
  net: number;
  cash_end: number;
  value?: number;
};

export type MetricTrend = {
  series: MetricSeriesRow[];
};

export type MonthlyTrendsResponse = {
  business_id: string;
  name: string;
  metrics?: Record<string, MetricTrend>;
  series?: TrendRow[];
};

export function useTrendsData(businessId: string, lookbackMonths: number, k = 2.0) {
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
  }, [businessId, k, lookbackMonths]);

  return { data, loading, err };
}
