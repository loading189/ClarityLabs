import { useCallback, useEffect, useState } from "react";
import {
  createSimIntervention,
  deleteSimIntervention,
  listSimInterventions,
  patchSimIntervention,
} from "../api/simulator";
import type { InterventionCreate, InterventionOut, InterventionPatch } from "../api/simulator";
import { useAppState } from "../app/state/appState";

export function useSimInterventions() {
  const { activeBusinessId, dataVersion } = useAppState();
  const businessId = activeBusinessId ?? null;
  const [data, setData] = useState<InterventionOut[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const refresh = useCallback(
    async (signal?: AbortSignal) => {
      if (!businessId) return;

      setLoading(true);
      setErr(null);

      try {
        const res = await listSimInterventions(businessId, { signal });
        setData(res);
      } catch (e: any) {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setErr(e?.message ?? "Failed to load interventions");
      } finally {
        setLoading(false);
      }
    },
    [businessId, dataVersion]
  );

  const create = useCallback(
    async (payload: InterventionCreate) => {
      if (!businessId) return null;
      const res = await createSimIntervention(businessId, payload);
      await refresh();
      return res;
    },
    [businessId, refresh]
  );

  const update = useCallback(
    async (interventionId: string, payload: InterventionPatch) => {
      if (!businessId) return null;
      const res = await patchSimIntervention(businessId, interventionId, payload);
      await refresh();
      return res;
    },
    [businessId, refresh]
  );

  const remove = useCallback(
    async (interventionId: string) => {
      if (!businessId) return null;
      const res = await deleteSimIntervention(businessId, interventionId);
      await refresh();
      return res;
    },
    [businessId, refresh]
  );

  useEffect(() => {
    if (!businessId) return undefined;
    const controller = new AbortController();
    refresh(controller.signal);
    return () => controller.abort();
  }, [businessId, refresh]);

  return { data, loading, err, refresh, create, update, remove };
}
