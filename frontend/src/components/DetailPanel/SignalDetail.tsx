// src/components/detail/SignalDetail.tsx
import type { HealthSignal } from "../../types";
import styles from "../../features/signals/HealthTab.module.css";

type Props = {
  businessId: string;
  signal: HealthSignal;
  onNavigate?: (
    target: "transactions" | "trends" | "categorize" | "ledger",
    drilldown?: Record<string, any> | null
  ) => void;
};

export default function SignalDetail({ businessId, signal, onNavigate }: Props) {
  void businessId;

  const drilldownButtons = (signal.drilldowns ?? []).map((d, idx) => {
    const label = d.label ?? "Open drilldown";
    const payload = d.payload ?? null;
    return (
      <button
        key={`${d.target}-${idx}`}
        className={styles.actionButton}
        onClick={() => onNavigate?.(d.target, payload as Record<string, any> | null)}
        type="button"
      >
        {label}
      </button>
    );
  });

  return (
    <div className={styles.signalDetail}>
      <div className={styles.signalDetailHeader}>
        <div>
          <div className={styles.signalDetailTitle}>{signal.title}</div>
          <div className={styles.signalDetailMeta}>
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
            <span className={`${styles.pill} ${styles.pillSoft}`}>{signal.status}</span>
            {signal.updated_at && <span className={styles.pill}>Updated {signal.updated_at}</span>}
          </div>
        </div>
      </div>

      <div className={styles.signalDetailMessage}>{signal.short_summary}</div>

      <div className={styles.signalDetailBlock}>
        <div className={styles.signalDetailLabel}>Why it matters</div>
        <div className={styles.signalDetailBody}>{signal.why_it_matters}</div>
      </div>

      <div className={styles.signalDetailBlock}>
        <div className={styles.signalDetailLabel}>Evidence</div>
        <div className={styles.signalEvidenceStack}>
          {(signal.evidence ?? []).map((ev, idx) => (
            <div key={idx} className={styles.signalEvidenceCard}>
              <div className={styles.signalEvidenceHeader}>
                <div className={styles.signalEvidenceTitle}>
                  {ev.date_range?.label || "Period"}
                </div>
                <div className={styles.signalEvidenceRange}>
                  {ev.date_range?.start} → {ev.date_range?.end}
                </div>
              </div>
              <div className={styles.signalEvidenceMetrics}>
                {Object.entries(ev.metrics ?? {}).map(([key, value]) => (
                  <div key={key} className={styles.signalEvidenceMetric}>
                    <div className={styles.signalEvidenceKey}>{key}</div>
                    <div className={styles.signalEvidenceValue}>{String(value)}</div>
                  </div>
                ))}
              </div>
              {ev.examples && ev.examples.length > 0 && (
                <div className={styles.signalEvidenceExamples}>
                  <div className={styles.signalEvidenceLabel}>Example transactions</div>
                  <div className={styles.signalEvidenceTable}>
                    {ev.examples.map((ex: any, i: number) => (
                      <div key={`${ex.source_event_id}-${i}`} className={styles.signalEvidenceRow}>
                        <div className={styles.noWrap}>{ex.date ?? ex.occurred_at ?? "—"}</div>
                        <div className={styles.signalEvidenceDesc}>
                          {ex.description ?? "—"}
                          <div className={styles.signalEvidenceSub}>
                            event {String(ex.source_event_id ?? "").slice(-6)}
                          </div>
                        </div>
                        <div className={styles.alignRight}>
                          {ex.amount != null
                            ? `${ex.direction === "outflow" ? "-" : ""}$${Number(
                                Math.abs(ex.amount)
                              ).toFixed(2)}`
                            : "—"}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {drilldownButtons.length > 0 && (
        <div className={styles.signalActions}>{drilldownButtons}</div>
      )}
    </div>
  );
}
