import { useEffect, useState } from "react";
import { fetchBusinessHealth } from "../api/demo";
import type { BusinessDetail } from "../types";

export function useBusinessDetailData(businessId: string) {
  const [data, setData] = useState<BusinessDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!businessId) return;
    const controller = new AbortController();
    setLoading(true);
    setErr(null);
    fetchBusinessHealth(businessId, controller.signal)
      .then((payload) => setData(payload))
      .catch((e: unknown) => {
        if (e instanceof DOMException && e.name === "AbortError") return;
        if (e instanceof Error) {
          setErr(e.message);
          return;
        }
        setErr("Failed to load business detail");
      })
      .finally(() => setLoading(false));

    return () => controller.abort();
  }, [businessId]);

  return { data, loading, err };
}
