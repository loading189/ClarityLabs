import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import PageHeader from "../../components/common/PageHeader";
import styles from "./IntegrationsPage.module.css";
import {
  disconnectIntegration,
  getIntegrationConnections,
  replayIntegration,
  syncIntegration,
  toggleIntegration,
  type IntegrationConnection,
} from "../../api/integrations";
import { assertBusinessId } from "../../utils/businessId";

function formatDate(value?: string | null) {
  if (!value) return "—";
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return value;
  return dt.toLocaleString();
}

function truncate(value?: string | null, max = 14) {
  if (!value) return "—";
  if (value.length <= max) return value;
  return `${value.slice(0, max)}…`;
}

export default function IntegrationsPage() {
  const { businessId: businessIdParam } = useParams();
  const businessId = assertBusinessId(businessIdParam, "IntegrationsPage");
  const [connections, setConnections] = useState<IntegrationConnection[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busyProvider, setBusyProvider] = useState<string | null>(null);

  const loadConnections = useCallback(async () => {
    if (!businessId) return;
    setLoading(true);
    setErr(null);
    try {
      const data = await getIntegrationConnections(businessId);
      setConnections(data);
    } catch (e: any) {
      setErr(e?.message ?? "Failed to load connections");
    } finally {
      setLoading(false);
    }
  }, [businessId]);

  useEffect(() => {
    loadConnections();
  }, [loadConnections]);

  const handleAction = useCallback(
    async (provider: string, action: () => Promise<any>) => {
      setBusyProvider(provider);
      setErr(null);
      try {
        await action();
        await loadConnections();
      } catch (e: any) {
        setErr(e?.message ?? "Integration action failed");
      } finally {
        setBusyProvider(null);
      }
    },
    [loadConnections]
  );

  const rows = useMemo(() => connections ?? [], [connections]);

  return (
    <div className={styles.page}>
      <PageHeader
        title="Integrations"
        subtitle="Connection status for banks, processors, and data providers."
      />

      {loading && <div className={styles.inlineMuted}>Loading connections…</div>}
      {err && <div className={styles.inlineError}>{err}</div>}

      <div className={styles.card}>
        <div className={styles.tableHeader}>
          <div>Provider</div>
          <div>Status</div>
          <div>Last sync</div>
          <div>Last success</div>
          <div>Last error</div>
          <div>Provider cursor</div>
          <div>Processing cursor</div>
          <div>Actions</div>
        </div>
        {rows.length === 0 && !loading && (
          <div className={styles.inlineMuted}>No integration connections yet.</div>
        )}
        {rows.map((conn) => {
          const busy = busyProvider === conn.provider;
          return (
            <div key={conn.id} className={styles.tableRow}>
              <div className={styles.providerLabel}>{conn.provider}</div>
              <div>
                <span className={`${styles.status} ${styles[`status_${conn.status}`] || ""}`}>
                  {conn.status}
                </span>
              </div>
              <div>{formatDate(conn.last_sync_at)}</div>
              <div>{formatDate(conn.last_success_at)}</div>
              <div className={styles.errorCell}>
                {conn.last_error_at ? formatDate(conn.last_error_at) : "—"}
                {conn.last_error?.message && (
                  <div className={styles.errorMessage}>{conn.last_error.message}</div>
                )}
              </div>
              <div className={styles.cursorCell}>
                <span>{truncate(conn.provider_cursor)}</span>
                {conn.provider_cursor && (
                  <button
                    className={styles.copyButton}
                    onClick={() => navigator.clipboard?.writeText(conn.provider_cursor || "")}
                  >
                    Copy
                  </button>
                )}
              </div>
              <div className={styles.cursorCell}>
                <span>{truncate(conn.last_processed_source_event_id)}</span>
                {conn.last_processed_source_event_id && (
                  <button
                    className={styles.copyButton}
                    onClick={() =>
                      navigator.clipboard?.writeText(conn.last_processed_source_event_id || "")
                    }
                  >
                    Copy
                  </button>
                )}
              </div>
              <div className={styles.actions}>
                <button
                  className={styles.actionButton}
                  disabled={busy}
                  onClick={() =>
                    handleAction(conn.provider, () =>
                      syncIntegration(businessId, conn.provider)
                    )
                  }
                >
                  Sync now
                </button>
                <button
                  className={styles.actionButton}
                  disabled={busy}
                  onClick={() =>
                    handleAction(conn.provider, () =>
                      toggleIntegration(businessId, conn.provider, !conn.is_enabled)
                    )
                  }
                >
                  {conn.is_enabled ? "Disable" : "Enable"}
                </button>
                <button
                  className={styles.actionButton}
                  disabled={busy}
                  onClick={() =>
                    handleAction(conn.provider, () =>
                      replayIntegration(businessId, conn.provider, {})
                    )
                  }
                >
                  Replay
                </button>
                <button
                  className={styles.destructiveButton}
                  disabled={busy}
                  onClick={() =>
                    handleAction(conn.provider, () =>
                      disconnectIntegration(businessId, conn.provider)
                    )
                  }
                >
                  Disconnect
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
