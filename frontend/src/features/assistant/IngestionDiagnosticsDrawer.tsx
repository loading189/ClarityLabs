import Drawer from "../../components/common/Drawer";
import type { IngestionDiagnostics } from "../../api/ingestionDiagnostics";
import styles from "./IngestionDiagnosticsDrawer.module.css";

function formatDate(value?: string | null) {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  return parsed.toLocaleString();
}

function formatCounts(counts: Record<string, number>) {
  return Object.entries(counts).sort((a, b) => a[0].localeCompare(b[0]));
}

type Props = {
  open: boolean;
  onClose: () => void;
  diagnostics: IngestionDiagnostics | null;
  loading: boolean;
  error: string | null;
};

export default function IngestionDiagnosticsDrawer({ open, onClose, diagnostics, loading, error }: Props) {
  return (
    <Drawer open={open} title="Ingestion diagnostics" onClose={onClose}>
      <div className={styles.body}>
        {loading && <div className={styles.subtle}>Loading ingestion diagnostics...</div>}
        {!loading && error && <div className={styles.error}>{error}</div>}
        {!loading && !error && !diagnostics && (
          <div className={styles.subtle}>No diagnostics available yet.</div>
        )}
        {!loading && !error && diagnostics && (
          <>
            <section className={styles.section}>
              <h4>Status counts</h4>
              <ul className={styles.list}>
                {formatCounts(diagnostics.status_counts).map(([status, count]) => (
                  <li key={status}>
                    <strong>{status}</strong>
                    <span>{count}</span>
                  </li>
                ))}
              </ul>
            </section>
            <section className={styles.section}>
              <h4>Integration cursors</h4>
              {diagnostics.connections.length ? (
                <ul className={styles.list}>
                  {diagnostics.connections.map((row) => (
                    <li key={row.provider}>
                      <div className={styles.rowHeader}>
                        <strong>{row.provider}</strong>
                        <span>{row.status}</span>
                      </div>
                      <div className={styles.rowMeta}>Last sync: {formatDate(row.last_sync_at)}</div>
                      <div className={styles.rowMeta}>
                        Last cursor: {row.last_cursor ?? "—"} · {formatDate(row.last_cursor_at)}
                      </div>
                      <div className={styles.rowMeta}>Last webhook: {formatDate(row.last_webhook_at)}</div>
                      {row.last_error && <div className={styles.error}>{row.last_error}</div>}
                    </li>
                  ))}
                </ul>
              ) : (
                <div className={styles.subtle}>No integration connections.</div>
              )}
            </section>
            <section className={styles.section}>
              <h4>Processing errors</h4>
              {diagnostics.errors.length ? (
                <ul className={styles.list}>
                  {diagnostics.errors.map((row) => (
                    <li key={`${row.source_event_id}-${row.provider}`}>
                      <div className={styles.rowHeader}>
                        <strong>{row.source_event_id}</strong>
                        <span>{row.provider}</span>
                      </div>
                      <div className={styles.rowMeta}>Code: {row.error_code ?? "—"}</div>
                      <div className={styles.rowMeta}>{row.error_detail ?? "No details"}</div>
                      <div className={styles.rowMeta}>Updated: {formatDate(row.updated_at)}</div>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className={styles.subtle}>No processing errors.</div>
              )}
            </section>
            <section className={styles.section}>
              <h4>Monitor status</h4>
              <div className={styles.rowMeta}>
                Status: {diagnostics.monitor_status?.stale ? "Stale" : "Fresh"}
              </div>
              <div className={styles.rowMeta}>
                Last pulse: {formatDate(diagnostics.monitor_status?.last_pulse_at)}
              </div>
              <div className={styles.rowMeta}>
                Newest event: {formatDate(diagnostics.monitor_status?.newest_event_at)}
              </div>
              {diagnostics.monitor_status?.gating_reason && (
                <div className={styles.rowMeta}>Gating: {diagnostics.monitor_status.gating_reason}</div>
              )}
            </section>
          </>
        )}
      </div>
    </Drawer>
  );
}
