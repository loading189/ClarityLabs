import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { listIntegrationConnections, type IntegrationConnection } from "../../api/integrationConnections";
import { createPlaidLinkToken, exchangePlaidPublicToken, syncPlaid } from "../../api/plaid";
import styles from "./IntegrationsPage.module.css";

function formatDate(value?: string | null) {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  return parsed.toLocaleString();
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
      await syncPlaid(businessId);
      setStatusMessage("Sync completed. Monitoring pulse ran.");
      await loadConnections();
    } catch (err: any) {
      setError(err?.message ?? "Failed to sync Plaid transactions.");
    }
  }, [businessId, loadConnections]);

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
        <h3>Connection health</h3>
        <div className={styles.statusRow}>
          <span className={styles.statusLabel}>Status</span>
          <span className={styles.statusValue}>{plaidConnection?.status ?? "disconnected"}</span>

          <span className={styles.statusLabel}>Last sync</span>
          <span className={styles.statusValue}>{formatDate(plaidConnection?.last_sync_at)}</span>

          <span className={styles.statusLabel}>Cursor</span>
          <span className={styles.statusValue}>{plaidConnection?.last_cursor ?? "—"}</span>

          <span className={styles.statusLabel}>Last error</span>
          <span className={styles.statusValue}>{plaidConnection?.last_error ?? "—"}</span>
        </div>
      </aside>
    </div>
  );
}
