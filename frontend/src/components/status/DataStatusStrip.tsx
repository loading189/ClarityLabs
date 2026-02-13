import { useCallback, useEffect, useState } from "react";
import { fetchDataStatus, type DataStatus } from "../../api/dataStatus";
import { InlineAlert } from "../ui";
import styles from "./DataStatusStrip.module.css";

function fmt(value?: string | null) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString();
}

export default function DataStatusStrip({ businessId, refreshKey }: { businessId: string; refreshKey?: number }) {
  const [status, setStatus] = useState<DataStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!businessId) return;
    try {
      setError(null);
      const data = await fetchDataStatus(businessId);
      setStatus(data);
    } catch (e: any) {
      setError(e?.message ?? "Failed to load data status.");
    }
  }, [businessId]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  if (!businessId) return null;

  return (
    <>
      {error && <InlineAlert tone="error" title="Data status unavailable" description={error} />}
      <div className={styles.strip}>
        <span className={styles.pill}><span className={styles.label}>Latest event:</span> {status?.latest_event?.source ?? "—"} · {fmt(status?.latest_event?.occurred_at)}</span>
        <span className={styles.pill}><span className={styles.label}>Open signals:</span> {status?.open_signals ?? "—"}</span>
        <span className={styles.pill}><span className={styles.label}>Open actions:</span> {status?.open_actions ?? "—"}</span>
        <span className={styles.pill}><span className={styles.label}>Ledger rows:</span> {status?.ledger_rows ?? "—"}</span>
        <span className={styles.pill}><span className={styles.label}>Uncategorized:</span> {status?.uncategorized_txns ?? "—"}</span>
        <span className={styles.pill}><span className={styles.label}>Last sync:</span> {fmt(status?.last_sync_at)}</span>
      </div>
    </>
  );
}
