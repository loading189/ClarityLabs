import { useEffect, useState } from "react";
import { fetchLedgerLines, type LedgerLine } from "../../api/ledger";

export function useLedgerLines(
  businessId: string,
  startDate: string,
  endDate: string,
  limit = 5000
) {
  const [lines, setLines] = useState<LedgerLine[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!businessId) return;
    const controller = new AbortController();
    setLoading(true);
    setErr(null);
    fetchLedgerLines(
      businessId,
      {
        start_date: startDate,
        end_date: endDate,
        limit,
      },
      controller.signal
    )
      .then((payload) => setLines(payload))
      .catch((e: unknown) => {
        if (e instanceof DOMException && e.name === "AbortError") return;
        if (e instanceof Error) {
          setErr(e.message);
          return;
        }
        setErr("Failed to load ledger");
      })
      .finally(() => setLoading(false));

    return () => controller.abort();
  }, [businessId, endDate, limit, startDate]);

  return { lines, loading, err };
}
