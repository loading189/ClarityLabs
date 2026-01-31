import { useCallback, useEffect, useState } from "react";
import { SimPlanOut, SimPlanUpsert, getSimPlan, putSimPlan } from "../api/simulator";

export function useSimPlan(businessId: string) {
  const [data, setData] = useState<SimPlanOut | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const refresh = useCallback(
    async (signal?: AbortSignal) => {
      if (!businessId) return;
      setLoading(true);
      setErr(null);

      try {
        const res = await getSimPlan(businessId, { signal });
        setData(res);
      } catch (e: any) {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setErr(e?.message ?? "Failed to load simulator plan");
      } finally {
        setLoading(false);
      }
    },
    [businessId]
  );

  const updatePlan = useCallback(
    async (payload: SimPlanUpsert) => {
      if (!businessId) return null;
      const res = await putSimPlan(businessId, payload);
      setData(res);
      return res;
    },
    [businessId]
  );

  useEffect(() => {
    if (!businessId) return undefined;
    const controller = new AbortController();
    refresh(controller.signal);
    return () => controller.abort();
  }, [businessId, refresh]);

  return {
    data,
    loading,
    err,
    refresh,
    updatePlan,
  };
}
