import { useEffect, useMemo, useState } from "react";
import type { SignalExplainEvidence } from "../../api/signals";
import { fetchLedgerTransactions, type LedgerTraceTxn } from "../../api/ledger";
import Drawer from "../common/Drawer";
import styles from "./LedgerTraceDrawer.module.css";

function formatAmount(amount: number, direction: "inflow" | "outflow") {
  const sign = direction === "outflow" ? "-" : "+";
  return `${sign}$${Math.abs(amount).toFixed(2)}`;
}

export default function LedgerTraceDrawer({
  open,
  onClose,
  businessId,
  anchors,
}: {
  open: boolean;
  onClose: () => void;
  businessId: string;
  anchors: SignalExplainEvidence["anchors"] | null;
}) {
  const [rows, setRows] = useState<LedgerTraceTxn[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const query = useMemo(() => {
    if (!anchors) return null;
    if (anchors.source_event_ids && anchors.source_event_ids.length > 0) {
      return { txn_ids: anchors.source_event_ids };
    }
    if (anchors.start_date && anchors.end_date) {
      return { date_start: anchors.start_date, date_end: anchors.end_date };
    }
    return null;
  }, [anchors]);

  useEffect(() => {
    let active = true;
    if (!open || !businessId || !query) return;
    setLoading(true);
    setErr(null);
    fetchLedgerTransactions(businessId, query)
      .then((data) => {
        if (!active) return;
        setRows(data);
      })
      .catch((error: Error) => {
        if (!active) return;
        setErr(error.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [businessId, open, query]);

  return (
    <Drawer open={open} title="Ledger trace" onClose={onClose}>
      {!query && <div className={styles.muted}>No anchors available for this evidence.</div>}
      {loading && <div className={styles.muted}>Loading transactions…</div>}
      {err && <div className={styles.error}>{err}</div>}
      {!loading && !err && query && (
        <div className={styles.list}>
          {rows.length === 0 && <div className={styles.muted}>No transactions found.</div>}
          {rows.map((row) => (
            <div key={row.source_event_id} className={styles.row}>
              <div>
                <div className={styles.description}>{row.description}</div>
                <div className={styles.meta}>
                  {new Date(row.occurred_at).toLocaleDateString()} · {row.category_name ?? "—"}
                </div>
              </div>
              <div className={styles.amount}>{formatAmount(row.display_amount, row.direction)}</div>
            </div>
          ))}
        </div>
      )}
    </Drawer>
  );
}
