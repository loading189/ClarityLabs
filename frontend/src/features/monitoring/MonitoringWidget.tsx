import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { runMonitorPulse } from "../../api/monitor";
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

function getLatestTimestamp(signals: SignalState[]) {
  return signals.reduce<string | null>((latest, signal) => {
    if (!signal.updated_at) return latest;
    if (!latest) return signal.updated_at;
    return new Date(signal.updated_at).getTime() > new Date(latest).getTime()
      ? signal.updated_at
      : latest;
  }, null);
}

export default function MonitoringWidget({ businessId }: { businessId: string }) {
  const [signals, setSignals] = useState<SignalState[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [pulseLoading, setPulseLoading] = useState(false);
  const [lastPulseAt, setLastPulseAt] = useState<string | null>(null);
  const [newestEventAt, setNewestEventAt] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!businessId) return;
    setLoading(true);
    setErr(null);
    try {
      const signalsData = await listSignalStates(businessId);
      const nextSignals = signalsData.signals ?? [];
      const latestTimestamp = getLatestTimestamp(nextSignals);
      setSignals(nextSignals);
      setLastPulseAt((prev) => {
        if (!latestTimestamp) return prev ?? null;
        if (!prev) return latestTimestamp;
        return new Date(latestTimestamp).getTime() > new Date(prev).getTime()
          ? latestTimestamp
          : prev;
      });
      setNewestEventAt((prev) => {
        if (!latestTimestamp) return prev ?? null;
        if (!prev) return latestTimestamp;
        return new Date(latestTimestamp).getTime() > new Date(prev).getTime()
          ? latestTimestamp
          : prev;
      });
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
  const openTotal = useMemo(
    () => signals.filter((signal) => signal.status === "open").length,
    [signals]
  );

  const handlePulse = async () => {
    if (!businessId || pulseLoading) return;
    setPulseLoading(true);
    setErr(null);
    try {
      const pulse = await runMonitorPulse(businessId);
      setLastPulseAt(pulse.last_pulse_at ?? null);
      setNewestEventAt(pulse.newest_event_at ?? null);
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
              <div className={styles.metricValue}>{formatDateTime(lastPulseAt)}</div>
            </div>
            <div>
              <div className={styles.metricLabel}>Newest event</div>
              <div className={styles.metricValue}>{formatDateTime(newestEventAt)}</div>
            </div>
            <div>
              <div className={styles.metricLabel}>Open alerts</div>
              <div className={styles.metricValue}>{openTotal}</div>
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
