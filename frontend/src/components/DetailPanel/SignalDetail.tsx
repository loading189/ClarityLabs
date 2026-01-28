// src/components/detail/SignalDetail.tsx
import { useMemo } from "react";
import type { Signal } from "../../types";
import type { TransactionsDrilldown } from "../../features/transactions";
import { useTransactions } from "../../hooks/useTransactions";
import styles from "../../features/signals/HealthTab.module.css";

type Props = {
  businessId: string;
  signal: Signal;
  onNavigate?: (target: "transactions" | "trends", drilldown?: TransactionsDrilldown | null) => void;
};

function extractSourceEventIds(signal: Signal): string[] {
  const refs = signal.evidence_refs ?? [];
  const ids = refs
    .map((r: any) => String(r?.source_event_id ?? "").trim())
    .filter(Boolean);
  return Array.from(new Set(ids));
}

export default function SignalDetail({ businessId, signal, onNavigate }: Props) {
  const sourceEventIds = useMemo(() => extractSourceEventIds(signal), [signal]);

  // Only fetch if we actually have refs
  const shouldFetch = sourceEventIds.length > 0;
  const { data, loading, err, refresh } = useTransactions(
    shouldFetch ? businessId : null,
    50,
    shouldFetch ? sourceEventIds : undefined
  );

  return (
    <div className={styles.signalDetail}>
      <div className={styles.signalDetailHeader}>
        <div>
          <div className={styles.signalDetailTitle}>{signal.title}</div>
          <div className={styles.signalDetailMeta}>
            <span className={`${styles.pill} ${styles.pillSoft}`}>{signal.dimension ?? "other"}</span>
            <span
              className={`${styles.pill} ${
                signal.severity === "red"
                  ? styles.pillRed
                  : signal.severity === "yellow"
                  ? styles.pillYellow
                  : styles.pillGreen
              }`}
            >
              {String(signal.severity ?? "green").toUpperCase()}
            </span>
            <span className={styles.pill}>Priority {signal.priority ?? 0}</span>
          </div>
        </div>

        {shouldFetch && (
          <button className={styles.actionButton} onClick={refresh} disabled={loading}>
            {loading ? "Loading…" : "Refresh"}
          </button>
        )}
      </div>

      <div className={styles.signalDetailMessage}>{signal.message}</div>

      {signal.why && (
        <div className={styles.signalDetailBlock}>
          <div className={styles.signalDetailLabel}>Why</div>
          <div className={styles.signalDetailBody}>{signal.why}</div>
        </div>
      )}

      {signal.how_to_fix && (
        <div className={styles.signalDetailBlock}>
          <div className={styles.signalDetailLabel}>Next step</div>
          <div className={styles.signalDetailBody}>{signal.how_to_fix}</div>
        </div>
      )}

      {signal.evidence && (
        <details className={styles.signalDetailDetails}>
          <summary>Evidence</summary>
          <pre>{JSON.stringify(signal.evidence, null, 2)}</pre>
        </details>
      )}

      <div className={styles.signalActions}>
        <button className={styles.actionButton} onClick={() => onNavigate?.("transactions")}>
          View transactions
        </button>
        <button className={styles.actionButton} onClick={() => onNavigate?.("trends")}>
          View trend
        </button>
      </div>

      {/* Drilldown transactions */}
      <div className={styles.signalDetailBlock}>
        <div className={styles.signalDetailLabel}>
          Related transactions {shouldFetch ? `(${sourceEventIds.length} refs)` : "(no refs)"}
        </div>

        {!shouldFetch && (
          <div className={styles.inlineMuted}>
            This signal doesn’t yet include transaction references (evidence_refs).
          </div>
        )}

        {shouldFetch && err && <div className={styles.inlineError}>Error loading transactions: {err}</div>}

        {shouldFetch && loading && !data && <div className={styles.inlineMuted}>Loading…</div>}

        {shouldFetch && data && (
          <div className={styles.signalTableWrap}>
            <table className={styles.signalTable}>
              <thead>
                <tr>
                  <th>When</th>
                  <th>Description</th>
                  <th>Account</th>
                  <th>Category</th>
                  <th className={styles.alignRight}>Amount</th>
                </tr>
              </thead>
              <tbody>
                {(data.transactions ?? []).map((t) => (
                  <tr key={t.id}>
                    <td className={styles.noWrap}>
                      {t.occurred_at ? new Date(t.occurred_at).toLocaleString() : "—"}
                    </td>
                    <td>
                      <div className={styles.tableTitle}>{t.description}</div>
                      <small className={styles.tableSub}>event {String(t.source_event_id).slice(-6)}</small>
                    </td>
                    <td>{t.account}</td>
                    <td>{t.category}</td>
                    <td className={styles.alignRight}>
                      {t.amount < 0 ? "-" : ""}${Math.abs(t.amount).toFixed(2)}
                    </td>
                  </tr>
                ))}
                {(data.transactions ?? []).length === 0 && (
                  <tr>
                    <td colSpan={5} className={styles.emptyCell}>
                      No matching transactions returned for these refs.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
