import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getMonitorStatus, runMonitorPulse, type MonitorStatus } from "../../api/monitor";
import { listSignalStates, type SignalState } from "../../api/signals";
import styles from "./MonitoringWidget.module.css";

function formatDateTime(value: string | null | undefined) {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  return parsed.toLocaleString();
}

function countOpenBySeverity(signals: SignalState[]) {
  return signals.reduce(
    (acc, signal) => {
      if (signal.status !== "open") return acc;
      const severity = signal.severity ?? "unknown";
      acc[severity] = (acc[severity] ?? 0) + 1;
      return acc;
    },
    {} as Record<string, number>
  );
}

export default function MonitoringWidget({ businessId }: { businessId: string }) {
  const [status, setStatus] = useState<MonitorStatus | null>(null);
  const [signals, setSignals] = useState<SignalState[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [pulseLoading, setPulseLoading] = useState(false);

  const load = useCallback(async () => {
    if (!businessId) return;
    setLoading(true);
    setErr(null);
    try {
      const [statusData, signalsData] = await Promise.all([
        getMonitorStatus(businessId),
        listSignalStates(businessId),
      ]);
      setStatus(statusData);
      setSignals(signalsData.signals ?? []);
    } catch (e: any) {
      setErr(e?.message ?? "Failed to load monitoring status");
    } finally {
      setLoading(false);
    }
  }, [businessId]);

  useEffect(() => {
    load();
  }, [load]);

  const openCounts = useMemo(() => countOpenBySeverity(signals), [signals]);

  const handlePulse = async () => {
    if (!businessId || pulseLoading) return;
    setPulseLoading(true);
    setErr(null);
    try {
      await runMonitorPulse(businessId);
      await load();
    } catch (e: any) {
      setErr(e?.message ?? "Failed to run monitor check");
    } finally {
      setPulseLoading(false);
    }
  };

  return (
    <section className={styles.card}>
      <div className={styles.header}>
        <div>
          <h4 className={styles.title}>Monitoring</h4>
          <div className={styles.subtitle}>Continuous signal checks and alert status.</div>
        </div>
        <div className={styles.headerActions}>
          <button
            className={styles.primaryButton}
            type="button"
            onClick={handlePulse}
            disabled={pulseLoading}
          >
            {pulseLoading ? "Running…" : "Run check now"}
          </button>
          <Link className={styles.linkButton} to={`/app/${businessId}/signals`}>
            View alerts
          </Link>
        </div>
      </div>

      {loading && <div className={styles.status}>Loading monitoring status…</div>}
      {err && <div className={styles.error}>{err}</div>}

      {!loading && !err && (
        <div className={styles.content}>
          <div className={styles.metrics}>
            <div>
              <div className={styles.metricLabel}>Last check</div>
              <div className={styles.metricValue}>{formatDateTime(status?.last_pulse_at)}</div>
            </div>
            <div>
              <div className={styles.metricLabel}>Newest event</div>
              <div className={styles.metricValue}>{formatDateTime(status?.newest_event_at)}</div>
            </div>
            <div>
              <div className={styles.metricLabel}>Open alerts</div>
              <div className={styles.metricValue}>{status?.open_count ?? 0}</div>
            </div>
          </div>
          <div className={styles.severityRow}>
            <div className={`${styles.severityBadge} ${styles.red}`}>
              <span>Red</span>
              <strong>{openCounts.red ?? 0}</strong>
            </div>
            <div className={`${styles.severityBadge} ${styles.yellow}`}>
              <span>Yellow</span>
              <strong>{openCounts.yellow ?? 0}</strong>
            </div>
            <div className={`${styles.severityBadge} ${styles.green}`}>
              <span>Green</span>
              <strong>{openCounts.green ?? 0}</strong>
            </div>
            <div className={styles.severityBadge}>
              <span>Other</span>
              <strong>{openCounts.unknown ?? 0}</strong>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
