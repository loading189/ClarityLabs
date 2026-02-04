import Drawer from "../common/Drawer";
import type { HealthScoreOut } from "../../api/healthScore";
import styles from "./HealthScoreBreakdownDrawer.module.css";

export default function HealthScoreBreakdownDrawer({
  open,
  onClose,
  score,
  onSelectSignal,
  getSignalLabel,
}: {
  open: boolean;
  onClose: () => void;
  score: HealthScoreOut | null;
  onSelectSignal?: (signalId: string) => void;
  getSignalLabel?: (signalId: string) => string | null;
}) {
  const contributors = score?.contributors ?? [];
  const domains = score?.domains ?? [];

  return (
    <Drawer open={open} title="Health score breakdown" onClose={onClose}>
      {!score && <div className={styles.muted}>No score available.</div>}
      {score && (
        <div className={styles.container}>
          <div className={styles.summary}>
            <div>
              <div className={styles.scoreLabel}>Overall score</div>
              <div className={styles.scoreValue}>{Math.round(score.score)}</div>
            </div>
            <div className={styles.meta}>Model: {score.meta.model_version}</div>
          </div>

          <div className={styles.section}>
            <div className={styles.sectionTitle}>Domains</div>
            <div className={styles.domainList}>
              {domains.map((domain) => (
                <div key={domain.domain} className={styles.domainRow}>
                  <span>{domain.domain}</span>
                  <span>{Math.round(domain.score)}</span>
                </div>
              ))}
            </div>
          </div>

          <div className={styles.section}>
            <div className={styles.sectionTitle}>Contributors</div>
            <div className={styles.contributorList}>
              {contributors.length === 0 && (
                <div className={styles.muted}>No active contributors.</div>
              )}
              {contributors.map((item) => (
                <button
                  key={item.signal_id}
                  type="button"
                  className={styles.contributorRow}
                  onClick={() => onSelectSignal?.(item.signal_id)}
                >
                  <div>
                    <div className={styles.contributorTitle}>
                      {getSignalLabel?.(item.signal_id) ?? item.signal_id}
                    </div>
                    <div className={styles.contributorMeta}>
                      {item.domain} · {item.status}
                    </div>
                    <div className={styles.contributorRationale}>{item.rationale}</div>
                  </div>
                  <div className={styles.contributorPenalty}>-{item.penalty.toFixed(1)}</div>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </Drawer>
  );
}
