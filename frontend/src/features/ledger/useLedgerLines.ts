// frontend/src/features/ledger/useLedgerLines.ts
import { useEffect, useState } from "react";
import { fetchLedgerLines, type LedgerLine } from "../../api/ledger";
import { useAppState } from "../../app/state/appState";
import { isValidIsoDate } from "../../app/filters/filters";
import { isBusinessIdValid } from "../../utils/businessId";

export function useLedgerLines(limit = 2000) {
  const { activeBusinessId, dateRange, dataVersion } = useAppState();
  const businessId = activeBusinessId ?? "";
  const { start: startDate, end: endDate } = dateRange;
  const [lines, setLines] = useState<LedgerLine[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!businessId) {
      setLines([]);
      setErr("Select a business to load ledger lines.");
      return;
    }
    if (!startDate || !endDate) {
      setLines([]);
      setErr("Select a date range to load ledger lines.");
      return;
    }
    if (!isBusinessIdValid(businessId)) {
      setLines([]);
      setErr("Invalid business id. Please re-select a business.");
      return;
    }
    if (!isValidIsoDate(startDate) || !isValidIsoDate(endDate) || startDate > endDate) {
      setLines([]);
      setErr(`Invalid date range: ${startDate} → ${endDate}`);
      return;
    }

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
  }, [businessId, startDate, endDate, limit, dataVersion]);

  return { lines, loading, err };
}
