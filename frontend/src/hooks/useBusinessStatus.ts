import { useCallback, useEffect, useState } from "react";
import { getBusinessStatus } from "../api/onboarding";
import type { BusinessStatusOut } from "../api/onboarding";
import { useAppState } from "../app/state/appState";

export function useBusinessStatus() {
  const { activeBusinessId, dataVersion } = useAppState();
  const businessId = activeBusinessId ?? null;
  const [data, setData] = useState<BusinessStatusOut | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const refresh = useCallback(
    async (signal?: AbortSignal) => {
      if (!businessId) return;
      setLoading(true);
      setErr(null);

      try {
        const res = await getBusinessStatus(businessId, { signal });
        setData(res);
      } catch (e: any) {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setErr(e?.message ?? "Failed to load business status");
      } finally {
        setLoading(false);
      }
    },
    [businessId, dataVersion]
  );

  useEffect(() => {
    if (!businessId) return undefined;
    const controller = new AbortController();
    refresh(controller.signal);
    return () => controller.abort();
  }, [businessId, refresh]);

  return { data, loading, err, refresh };
}
