// frontend/src/features/ledger/useLedgerLines.ts
import { useEffect, useState } from "react";
import { fetchLedgerLines, type LedgerLine } from "../../api/ledger";

export function useLedgerLines(
  businessId: string,
  startDate: string,
  endDate: string,
  limit = 2000
) {
  const [lines, setLines] = useState<LedgerLine[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!businessId || !startDate || !endDate) return;

    const controller = new AbortController();
    let alive = true;

    setLoading(true);
    setErr(null);

    fetchLedgerLines(
      businessId,
      { start_date: startDate, end_date: endDate, limit },
      controller.signal
    )
      .then((payload) => {
        if (!alive) return;
        setLines(payload);
      })
      .catch((e: unknown) => {
        if (!alive) return;
        if (e instanceof DOMException && e.name === "AbortError") return;
        if (e instanceof Error) setErr(e.message);
        else setErr("Failed to load ledger");
      })
      .finally(() => {
        if (!alive) return;
        setLoading(false);
      });

    return () => {
      alive = false;
      controller.abort();
    };
  }, [businessId, startDate, endDate, limit]);

  return { lines, loading, err };
}
