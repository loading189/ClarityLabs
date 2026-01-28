import { useEffect, useState } from "react";
import SimulatorTab from "./simulatorTab";
import { SignalsTab } from "../../features/signals";
import { CategorizeTab, type CategorizeDrilldown } from "../../features/categorize";
import { TransactionsTab, type TransactionsDrilldown } from "../../features/transactions";
import CoaTab from "./CoaTab";
import { LedgerTab, type LedgerDrilldown } from "../../features/ledger";
import { deleteBusiness } from "../../api/admin"; // ✅ add this (adjust path if needed)
import { TrendsTab, type TrendsDrilldown } from "../../features/trends";
import styles from "./DetailPanel.module.css";
import { logRefresh } from "../../utils/refreshLog";

type PanelMode = "simulator" |"coa" | "transactions" | "categorize" | "ledger" | "signals" | "trends";

export default function DetailPanel({
  state,
  onAfterPulse,
}: {
  state: any; // type later from your hook
  onAfterPulse?: () => void;
}) {
  const { selectedId, detail, loading, error, close, refreshDetail } = state;

  const [mode, setMode] = useState<PanelMode>("signals");
  const [refreshKey, setRefreshKey] = useState(0);
  const [transactionsDrilldown, setTransactionsDrilldown] = useState<TransactionsDrilldown | null>(
    null
  );
  const [categorizeDrilldown, setCategorizeDrilldown] = useState<CategorizeDrilldown | null>(null);
  const [ledgerDrilldown, setLedgerDrilldown] = useState<LedgerDrilldown | null>(null);
  const [trendsDrilldown, setTrendsDrilldown] = useState<TrendsDrilldown | null>(null);
  const [ledgerRefreshToken, setLedgerRefreshToken] = useState(0);
  const [trendsRefreshToken, setTrendsRefreshToken] = useState(0);
  const [signalsRefreshToken, setSignalsRefreshToken] = useState(0);

  // ✅ delete UI state
  const [dangerOpen, setDangerOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [deleteErr, setDeleteErr] = useState<string | null>(null);

  // When you open a new business, default back to Health
  useEffect(() => {
    if (selectedId) {
      setMode("signals");
      setRefreshKey((k) => k + 1); // force tabs to re-load when business changes
      setTransactionsDrilldown(null);
      setCategorizeDrilldown(null);
      setLedgerDrilldown(null);
      setTrendsDrilldown(null);
      setLedgerRefreshToken(0);
      setTrendsRefreshToken(0);
      setSignalsRefreshToken(0);

      // ✅ reset delete UI when switching businesses
      setDangerOpen(false);
      setTyped("");
      setDeleting(false);
      setDeleteErr(null);
    }
  }, [selectedId]);

  if (!selectedId) return null;

  const TabButton = ({ label, value }: { label: string; value: PanelMode }) => (
    <button
      className={`${styles.tabButton} ${mode === value ? styles.tabButtonActive : ""}`}
      onClick={() => setMode(value)}
      type="button"
    >
      {label}
    </button>
  );

  function bumpRefresh() {
    setRefreshKey((k) => k + 1);
  }

  function handleCategorizationChange() {
    if (selectedId) {
      logRefresh("health", "detail-refresh");
      refreshDetail?.(selectedId);
    }
    setLedgerRefreshToken((value) => value + 1);
    setTrendsRefreshToken((value) => value + 1);
    setSignalsRefreshToken((value) => value + 1);
    onAfterPulse?.();
  }

  // ✅ typed confirmation phrase
  const confirmPhrase = `delete ${detail?.name ?? selectedId}`;
  const canDelete = typed.trim().toLowerCase() === confirmPhrase.toLowerCase();

  async function onDelete() {
    if (!selectedId) return;
    if (!canDelete) return;

    setDeleting(true);
    setDeleteErr(null);

    try {
      await deleteBusiness(selectedId);

      // close the panel + let parent refresh business list/cards
      close?.();
      onAfterPulse?.();
    } catch (e: any) {
      setDeleteErr(e?.message ?? "Failed to delete business");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <div>
          <div className={styles.panelTitle}>{detail?.name ?? selectedId}</div>
          <div className={styles.panelSub}>
            Score: <strong>{detail?.health_score ?? "—"}</strong>
          </div>

          <div className={styles.tabRow}>
            <TabButton label="Simulator" value="simulator" />
            <TabButton label="COA" value="coa" />
            <TabButton label="Transactions" value="transactions" />
            <TabButton label="Categorize" value="categorize" />
            <TabButton label="Ledger" value="ledger" />
            <TabButton label="Trends" value="trends" />
            <TabButton label="Health" value="signals" />

            {/* ✅ Delete button lives here */}
            <button
              className={`${styles.tabButton} ${styles.dangerButton}`}
              onClick={() => {
                setDangerOpen((v) => !v);
                setDeleteErr(null);
              }}
              disabled={deleting}
              title="Delete this business and all associated data"
              type="button"
            >
              Delete…
            </button>
          </div>

          {/* ✅ Danger zone inline confirm */}
          {dangerOpen && (
            <div className={styles.dangerZone}>
              <div className={styles.dangerText}>
                Danger zone: this permanently deletes the business and all associated data.
              </div>

              <div className={styles.dangerHint}>
                Type <strong>{confirmPhrase}</strong> to confirm.
              </div>

              <input
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
                placeholder={confirmPhrase}
                disabled={deleting}
                className={styles.dangerInput}
              />

              {deleteErr && (
                <div className={styles.dangerError}>{deleteErr}</div>
              )}

              <div className={styles.dangerActions}>
                <button
                  className={`${styles.tabButton} ${styles.dangerButton}`}
                  onClick={onDelete}
                  disabled={!canDelete || deleting}
                  type="button"
                >
                  {deleting ? "Deleting…" : "Confirm delete"}
                </button>

                <button
                  className={styles.tabButton}
                  onClick={() => {
                    setDangerOpen(false);
                    setTyped("");
                    setDeleteErr(null);
                  }}
                  disabled={deleting}
                  type="button"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>

        <button className={styles.closeButton} onClick={close} disabled={deleting} type="button">
          Close
        </button>
      </div>

      {/* Body */}
      {loading && <div className={styles.panelStatus}>Loading…</div>}
      {error && <div className={styles.panelError}>Error: {error}</div>}

      {!loading && !error && (
        <div className={styles.panelBody}>
          {mode === "simulator" && (
            <SimulatorTab
              businessId={selectedId}
              onAfterPulse={() => {
                refreshDetail?.(selectedId);
                bumpRefresh();
                onAfterPulse?.();
              }}
              onAfterSave={() => {
                refreshDetail?.(selectedId);
                bumpRefresh();
                onAfterPulse?.();
              }}
            />
          )}  
          {mode === "coa" && <CoaTab key={`coa-${selectedId}-${refreshKey}`} businessId={selectedId} />}
          

          {mode === "transactions" && (
            <TransactionsTab
              key={`txn-${selectedId}-${refreshKey}`}
              businessId={selectedId}
              drilldown={transactionsDrilldown}
              onClearDrilldown={() => setTransactionsDrilldown(null)}
              onCategorizationChange={handleCategorizationChange}
            />
          )}

          {mode === "categorize" && (
            <CategorizeTab
              key={`cat-${selectedId}-${refreshKey}`}
              businessId={selectedId}
              drilldown={categorizeDrilldown}
              onClearDrilldown={() => setCategorizeDrilldown(null)}
              onCategorizationChange={handleCategorizationChange}
            />
          )}

          {mode === "ledger" && (
            <LedgerTab
              key={`led-${selectedId}-${refreshKey}`}
              businessId={selectedId}
              drilldown={ledgerDrilldown}
              refreshToken={ledgerRefreshToken}
              onClearDrilldown={() => setLedgerDrilldown(null)}
            />
          )}
          {mode === "signals" && detail && (
            <SignalsTab
              detail={detail}
              refreshToken={signalsRefreshToken}
              onNavigate={(target, drilldown) => {
                if (target === "transactions") {
                  setTransactionsDrilldown((drilldown ?? null) as TransactionsDrilldown | null);
                }
                if (target === "categorize") {
                  setCategorizeDrilldown((drilldown ?? null) as CategorizeDrilldown | null);
                }
                if (target === "ledger") {
                  setLedgerDrilldown((drilldown ?? null) as LedgerDrilldown | null);
                }
                if (target === "trends") {
                  setTrendsDrilldown((drilldown ?? null) as TrendsDrilldown | null);
                }
                setMode(target);
              }}
            />
          )}
      
          {mode === "trends" && (
            <TrendsTab
              key={`trends-${selectedId}-${refreshKey}`}
              businessId={selectedId}
              drilldown={trendsDrilldown}
              refreshToken={trendsRefreshToken}
              onClearDrilldown={() => setTrendsDrilldown(null)}
            />
          )}

        </div>
      )}
    </div>
  );
}
