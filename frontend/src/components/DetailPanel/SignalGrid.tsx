import type { HealthSignal } from "../../types";
import styles from "../../features/signals/HealthTab.module.css";

type Props = {
  signals: HealthSignal[];
  selectedKey?: string | null;
  onSelect: (sig: HealthSignal) => void;
};

function sevRank(sev?: string) {
  if (sev === "red") return 3;
  if (sev === "yellow") return 2;
  return 1;
}

export default function SignalGrid({ signals, selectedKey, onSelect }: Props) {
  const severityClass = (sev?: string) => {
    if (sev === "red") return styles.signalLightRed;
    if (sev === "yellow") return styles.signalLightYellow;
    return styles.signalLightGreen;
  };

  const sorted = [...signals].sort((a, b) => {
    const r = sevRank(b.severity) - sevRank(a.severity);
    if (r !== 0) return r;
    return String(a.id).localeCompare(String(b.id));
  });

  return (
    <div className={styles.signalGridWrap}>
      <div className={styles.signalGridHeader}>
        <div className={styles.signalGridTitle}>Signal Inbox</div>
        <div className={styles.signalGridHint}>Click a signal to review evidence and actions.</div>
      </div>

      <div className={styles.signalInboxList}>
        {sorted.map((s) => {
          const active = selectedKey === s.id;
          return (
            <button
              key={s.id}
              className={[
                styles.signalInboxItem,
                severityClass(s.severity),
                active ? styles.signalInboxActive : "",
              ].join(" ")}
              onClick={() => onSelect(s)}
              type="button"
            >
              <div className={styles.signalInboxBadge}>
                <div className={styles.signalInboxSeverity}>{String(s.severity).toUpperCase()}</div>
                <div className={styles.signalInboxStatus}>
                  {String(s.status ?? "open").replace(/_/g, " ")}
                </div>
              </div>
              <div className={styles.signalInboxBody}>
                <div className={styles.signalInboxTitle}>{s.title}</div>
                <div className={styles.signalInboxSummary}>{s.short_summary}</div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
