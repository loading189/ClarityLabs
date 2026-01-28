import { useEffect, useState } from "react";
import SimulatorTab from "./simulatorTab";
import { SignalsTab } from "../../features/signals";
import { CategorizeTab } from "../../features/categorize";
import { TransactionsTab, type TransactionsDrilldown } from "../../features/transactions";
import CoaTab from "./CoaTab";
import { LedgerTab } from "../../features/ledger";
import { deleteBusiness } from "../../api/admin"; // ✅ add this (adjust path if needed)
import { TrendsTab } from "../../features/trends";

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
      className="closeBtn"
      onClick={() => setMode(value)}
      style={{ opacity: mode === value ? 1 : 0.6 }}
    >
      {label}
    </button>
  );

  function bumpRefresh() {
    setRefreshKey((k) => k + 1);
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
    <div className="panel">
      <div className="panelHeader">
        <div>
          <div className="panelTitle">{detail?.name ?? selectedId}</div>
          <div className="panelSub">
            Score: <strong>{detail?.health_score ?? "—"}</strong>
          </div>

          <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
            <TabButton label="Simulator" value="simulator" />
            <TabButton label="COA" value="coa" />
            <TabButton label="Transactions" value="transactions" />
            <TabButton label="Categorize" value="categorize" />
            <TabButton label="Ledger" value="ledger" />
            <TabButton label="Trends" value="trends" />
            <TabButton label="Health" value="signals" />

            {/* ✅ Delete button lives here */}
            <button
              className="closeBtn"
              onClick={() => {
                setDangerOpen((v) => !v);
                setDeleteErr(null);
              }}
              style={{
                marginLeft: 8,
                border: "1px solid #ef4444",
                color: "#991b1b",
                opacity: deleting ? 0.6 : 0.9,
              }}
              disabled={deleting}
              title="Delete this business and all associated data"
            >
              Delete…
            </button>
          </div>

          {/* ✅ Danger zone inline confirm */}
          {dangerOpen && (
            <div
              style={{
                marginTop: 10,
                padding: 10,
                borderRadius: 12,
                border: "1px solid #fecaca",
                background: "rgba(254, 202, 202, 0.15)",
                maxWidth: 520,
              }}
            >
              <div style={{ fontSize: 12, color: "#991b1b", marginBottom: 6 }}>
                Danger zone: this permanently deletes the business and all associated data.
              </div>

              <div style={{ fontSize: 12, opacity: 0.85, marginBottom: 8 }}>
                Type <strong>{confirmPhrase}</strong> to confirm.
              </div>

              <input
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
                placeholder={confirmPhrase}
                disabled={deleting}
                style={{
                  width: "100%",
                  padding: 10,
                  borderRadius: 10,
                  border: "1px solid #e5e7eb",
                  marginBottom: 8,
                }}
              />

              {deleteErr && (
                <div style={{ color: "#b91c1c", fontSize: 12, marginBottom: 8 }}>
                  {deleteErr}
                </div>
              )}

              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button
                  className="closeBtn"
                  onClick={onDelete}
                  disabled={!canDelete || deleting}
                  style={{
                    border: "1px solid #ef4444",
                    opacity: !canDelete || deleting ? 0.6 : 1,
                  }}
                >
                  {deleting ? "Deleting…" : "Confirm delete"}
                </button>

                <button
                  className="closeBtn"
                  onClick={() => {
                    setDangerOpen(false);
                    setTyped("");
                    setDeleteErr(null);
                  }}
                  disabled={deleting}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>

        <button className="closeBtn" onClick={close} disabled={deleting}>
          Close
        </button>
      </div>

      {/* Body */}
      {loading && <div>Loading…</div>}
      {error && <div style={{ color: "#b91c1c" }}>Error: {error}</div>}

      {!loading && !error && (
        <div style={{ paddingTop: 8 }}>
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
            />
          )}

          {mode === "categorize" && (
            <CategorizeTab key={`cat-${selectedId}-${refreshKey}`} businessId={selectedId} />
          )}

          {mode === "ledger" && (
            <LedgerTab key={`led-${selectedId}-${refreshKey}`} businessId={selectedId} />
          )}
          {mode === "signals" && detail && (
            <SignalsTab
              detail={detail}
              onNavigate={(target, drilldown) => {
                if (target === "transactions") {
                  setTransactionsDrilldown(drilldown ?? null);
                }
                setMode(target);
              }}
            />
          )}
      
          {mode === "trends" && (
            <TrendsTab key={`trends-${selectedId}-${refreshKey}`} businessId={selectedId} />
          )}

        </div>
      )}
    </div>
  );
}
