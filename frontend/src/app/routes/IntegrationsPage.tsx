import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import {
  listIntegrationConnections,
  type IntegrationConnection,
  syncIntegration,
  replayIntegration,
  disableIntegration,
  enableIntegration,
  disconnectIntegration,
} from "../../api/integrationConnections";
import { createPlaidLinkToken, exchangePlaidPublicToken } from "../../api/plaid";
import styles from "./IntegrationsPage.module.css";

function formatDate(value?: string | null) {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  return parsed.toLocaleString();
}

function truncate(value?: string | null, max = 12) {
  if (!value) return "—";
  if (value.length <= max) return value;
  return `${value.slice(0, max)}…`;
}

export default function IntegrationsPage() {
  const { businessId } = useParams();
  const [connections, setConnections] = useState<IntegrationConnection[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [publicToken, setPublicToken] = useState("");
  const [linkToken, setLinkToken] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const plaidConnection = useMemo(
    () => connections.find((row) => row.provider === "plaid"),
    [connections]
  );

  const loadConnections = useCallback(async () => {
    if (!businessId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await listIntegrationConnections(businessId);
      setConnections(data);
    } catch (err: any) {
      setError(err?.message ?? "Failed to load integrations.");
    } finally {
      setLoading(false);
    }
  }, [businessId]);

  useEffect(() => {
    void loadConnections();
  }, [loadConnections]);

  const handleCreateLinkToken = useCallback(async () => {
    if (!businessId) return;
    setStatusMessage(null);
    setError(null);
    try {
      const data = await createPlaidLinkToken(businessId);
      setLinkToken(data.link_token);
      setStatusMessage("Link token generated. Paste it into Plaid Link if needed.");
    } catch (err: any) {
      setError(err?.message ?? "Failed to create link token.");
    }
  }, [businessId]);

  const handleExchange = useCallback(async () => {
    if (!businessId || !publicToken.trim()) return;
    setStatusMessage(null);
    setError(null);
    try {
      await exchangePlaidPublicToken(businessId, publicToken.trim());
      setPublicToken("");
      setStatusMessage("Plaid Sandbox connected.");
      await loadConnections();
    } catch (err: any) {
      setError(err?.message ?? "Failed to exchange public token.");
    }
  }, [businessId, loadConnections, publicToken]);

  const handleSync = useCallback(async () => {
    if (!businessId) return;
    setStatusMessage(null);
    setError(null);
    try {
      await syncIntegration(businessId, "plaid");
      setStatusMessage("Sync completed. Monitoring pulse ran.");
      await loadConnections();
    } catch (err: any) {
      setError(err?.message ?? "Failed to sync Plaid transactions.");
    }
  }, [businessId, loadConnections]);

  const handleSyncConnection = useCallback(
    async (provider: string) => {
      if (!businessId) return;
      setStatusMessage(null);
      setError(null);
      try {
        await syncIntegration(businessId, provider);
        setStatusMessage(`Sync completed for ${provider}.`);
        await loadConnections();
      } catch (err: any) {
        setError(err?.message ?? `Failed to sync ${provider}.`);
      }
    },
    [businessId, loadConnections]
  );

  const handleReplay = useCallback(
    async (provider: string) => {
      if (!businessId) return;
      setStatusMessage(null);
      setError(null);
      try {
        await replayIntegration(businessId, provider);
        setStatusMessage(`Replay completed for ${provider}.`);
        await loadConnections();
      } catch (err: any) {
        setError(err?.message ?? `Failed to replay ${provider} ingest.`);
      }
    },
    [businessId, loadConnections]
  );

  const handleToggle = useCallback(
    async (connection: IntegrationConnection) => {
      if (!businessId) return;
      setStatusMessage(null);
      setError(null);
      try {
        if (connection.is_enabled) {
          await disableIntegration(businessId, connection.provider);
        } else {
          await enableIntegration(businessId, connection.provider);
        }
        await loadConnections();
      } catch (err: any) {
        setError(err?.message ?? "Failed to toggle integration.");
      }
    },
    [businessId, loadConnections]
  );

  const handleDisconnect = useCallback(
    async (provider: string) => {
      if (!businessId) return;
      setStatusMessage(null);
      setError(null);
      try {
        await disconnectIntegration(businessId, provider);
        await loadConnections();
      } catch (err: any) {
        setError(err?.message ?? `Failed to disconnect ${provider}.`);
      }
    },
    [businessId, loadConnections]
  );

  const handleCopy = useCallback(async (value?: string | null) => {
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      setStatusMessage("Copied to clipboard.");
    } catch {
      setError("Copy failed.");
    }
  }, []);

  return (
    <div className={styles.layout}>
      <section className={styles.panelCard}>
        <h2>Integrations</h2>
        <p className={styles.subtleText}>
          Connect Plaid Sandbox to ingest live transactions. Use the dev-only public token flow for now.
        </p>

        <div className={styles.fieldRow}>
          <input
            placeholder="Paste Plaid public_token"
            value={publicToken}
            onChange={(event) => setPublicToken(event.target.value)}
          />
          <button className={styles.button} type="button" onClick={handleExchange} disabled={loading}>
            Connect
          </button>
        </div>

        <div className={styles.buttonGroup}>
          <button className={styles.buttonSecondary} type="button" onClick={handleCreateLinkToken}>
            Generate link token
          </button>
          <button
            className={styles.button}
            type="button"
            onClick={handleSync}
            disabled={!plaidConnection || loading}
          >
            Sync now
          </button>
        </div>

        {linkToken && (
          <div className={styles.statusRow}>
            <span className={styles.statusLabel}>Link token</span>
            <span className={styles.statusValue}>{linkToken}</span>
          </div>
        )}

        {statusMessage && <div className={styles.success}>{statusMessage}</div>}
        {error && <div className={styles.error}>{error}</div>}
      </section>

      <aside className={styles.panelCard}>
        <h3>Connections</h3>
        {connections.length ? (
          <div className={styles.connectionList}>
            {connections.map((connection) => (
              <div key={connection.provider} className={styles.connectionCard}>
                <div className={styles.connectionHeader}>
                  <strong>{connection.provider}</strong>
                  <span className={styles.statusBadge}>{connection.status}</span>
                </div>
                <div className={styles.connectionMeta}>
                  <div>
                    <span className={styles.statusLabel}>Last sync</span>
                    <span className={styles.statusValue}>{formatDate(connection.last_sync_at)}</span>
                  </div>
                  <div>
                    <span className={styles.statusLabel}>Last success</span>
                    <span className={styles.statusValue}>{formatDate(connection.last_success_at)}</span>
                  </div>
                  <div>
                    <span className={styles.statusLabel}>Last error</span>
                    <span className={styles.statusValue}>{connection.last_error ?? "—"}</span>
                  </div>
                  <div>
                    <span className={styles.statusLabel}>Provider cursor</span>
                    <span className={styles.statusValue}>{truncate(connection.last_cursor)}</span>
                    <button
                      type="button"
                      className={styles.copyButton}
                      onClick={() => handleCopy(connection.last_cursor)}
                    >
                      Copy
                    </button>
                  </div>
                  <div>
                    <span className={styles.statusLabel}>Processing cursor</span>
                    <span className={styles.statusValue}>
                      {truncate(connection.last_processed_source_event_id)}
                    </span>
                    <button
                      type="button"
                      className={styles.copyButton}
                      onClick={() => handleCopy(connection.last_processed_source_event_id)}
                    >
                      Copy
                    </button>
                  </div>
                </div>
                <div className={styles.connectionActions}>
                  <button type="button" onClick={() => handleSyncConnection(connection.provider)}>
                    Sync now
                  </button>
                  <button type="button" onClick={() => handleReplay(connection.provider)}>
                    Replay
                  </button>
                  <button type="button" onClick={() => handleToggle(connection)}>
                    {connection.is_enabled ? "Disable" : "Enable"}
                  </button>
                  <button type="button" onClick={() => handleDisconnect(connection.provider)}>
                    Disconnect
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className={styles.subtleText}>No integrations connected yet.</div>
        )}
      </aside>
    </div>
  );
}
