import { useState } from "react";
import { fetchBusinessHealth } from "../api/demo";
import type { BusinessDetail } from "../types";

export function useBusinessDetail() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<BusinessDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function open(id: string) {
    setSelectedId(id);
    setDetail(null);
    setErr(null);
    setLoading(true);
    try {
      const d = await fetchBusinessHealth(id);
      setDetail(d);
    } catch (e: any) {
      setErr(e?.message ?? "Failed to load business detail");
    } finally {
      setLoading(false);
    }
  }

  async function refresh() {
    if (!selectedId) return;
    setErr(null);
    setLoading(true);
    try {
      const d = await fetchBusinessHealth(selectedId);
      setDetail(d);
    } catch (e: any) {
      setErr(e?.message ?? "Failed to refresh business detail");
    } finally {
      setLoading(false);
    }
  }

  function close() {
    setSelectedId(null);
    setDetail(null);
    setErr(null);
    setLoading(false);
  }

  return { selectedId, detail, err, loading, open, refresh, close };
}
