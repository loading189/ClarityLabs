import { useCallback, useEffect, useState } from "react";
import { fetchBusinessesMine, type BusinessMembershipSummary } from "../api/businesses";

export function useBusinessesMine() {
  const [businesses, setBusinesses] = useState<BusinessMembershipSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetchBusinessesMine();
      setBusinesses(response ?? []);
    } catch (err: any) {
      setError(err?.message ?? "Failed to load businesses");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return { businesses, loading, error, reload: load };
}
