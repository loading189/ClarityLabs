import { useCallback, useEffect, useRef, useState } from "react";
import { fetchBusinessDashboard } from "../api/demo";
import type { DashboardDetail } from "../types";
import { useAppState } from "../app/state/appState";
import { isBusinessIdValid } from "../utils/businessId";

export function useDemoDashboard() {
  const { activeBusinessId, dataVersion } = useAppState();
  const businessId = activeBusinessId ?? "";
  const [data, setData] = useState<DashboardDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const seqRef = useRef(0);

  const load = useCallback(async (signal?: AbortSignal) => {
    if (!businessId) return;
    if (!isBusinessIdValid(businessId)) {
      setErr("Invalid business id. Please re-select a business.");
      return;
    }
    const seq = (seqRef.current += 1);
    setLoading(true);
    setErr(null);
    try {
      const payload = await fetchBusinessDashboard(businessId, signal);
      if (seq !== seqRef.current) return;
      setData(payload);
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      if (seq !== seqRef.current) return;
      if (e instanceof Error) {
        setErr(e.message);
      } else {
        setErr("Failed to load dashboard");
      }
    } finally {
      if (seq === seqRef.current) {
        setLoading(false);
      }
    }
  }, [businessId, dataVersion]);

  useEffect(() => {
    if (!businessId) return;
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [businessId, load]);

  return { data, loading, err, refresh: load };
}
