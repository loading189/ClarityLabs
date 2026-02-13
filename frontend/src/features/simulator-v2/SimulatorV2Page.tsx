import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getSimV2Catalog, resetSimV2, seedSimV2, type SimCatalog, type SimSeedResponse } from "../../api/simV2";
import { useAppState } from "../../app/state/appState";
import { ensureDynamicPlaidItem, pumpPlaidTransactions, type PlaidPumpResponse } from "../../api/plaid";

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

export default function SimulatorV2Page() {
  const { businessId = "" } = useParams();
  const { bumpDataVersion } = useAppState();
  const [catalog, setCatalog] = useState<SimCatalog | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<SimSeedResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedBusinessId, setSelectedBusinessId] = useState(businessId);
  const [scenarioId, setScenarioId] = useState("baseline_stable");
  const [anchorDate, setAnchorDate] = useState(todayIso());
  const [pumpStartDate, setPumpStartDate] = useState(todayIso());
  const [pumpEndDate, setPumpEndDate] = useState(todayIso());
  const [dailyTxnCount, setDailyTxnCount] = useState(25);
  const [profile, setProfile] = useState<"retail" | "services" | "ecom" | "mixed">("mixed");
  const [pumpTelemetry, setPumpTelemetry] = useState<PlaidPumpResponse | null>(null);

  useEffect(() => {
    getSimV2Catalog()
      .then((data) => {
        setCatalog(data);
        if (data.scenarios.length > 0) setScenarioId(data.scenarios[0].id);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  const runSeed = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await seedSimV2({
        business_id: selectedBusinessId,
        scenario_id: scenarioId,
        params: { anchor_date: anchorDate, refresh_actions: true },
      });
      setResult(res);
      bumpDataVersion();
    } catch (e: any) {
      setError(e?.message ?? "Seed failed");
    } finally {
      setLoading(false);
    }
  };

  const onReset = async () => {
    await resetSimV2(selectedBusinessId);
    bumpDataVersion();
    setResult(null);
  };

  return (
    <div style={{ padding: 24 }}>
      <h2>Scenario Tools</h2>
      <div style={{ display: "flex", gap: 12 }}>
        <label>
          Business
          <input value={selectedBusinessId} onChange={(e) => setSelectedBusinessId(e.target.value)} />
        </label>
        <label>
          Scenario
          <select value={scenarioId} onChange={(e) => setScenarioId(e.target.value)}>
            {catalog?.scenarios.map((s) => (
              <option value={s.id} key={s.id}>{s.name}</option>
            ))}
          </select>
        </label>
        <label>
          Anchor
          <input value={anchorDate} onChange={(e) => setAnchorDate(e.target.value)} />
        </label>
      </div>
      <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
        <button onClick={runSeed} disabled={loading || !selectedBusinessId}>Seed</button>
        <button onClick={onReset} disabled={!selectedBusinessId}>Reset</button>
      </div>
      {error && <div style={{ color: "crimson" }}>{error}</div>}

      {result && (
        <div style={{ marginTop: 16 }}>
          <div>Scenario: {result.scenario_id}</div>
          <div>Seed key: {result.seed_key}</div>
          <div>Transactions created: {result.summary.txns_created}</div>
          <div>Ledger rows: {result.summary.ledger_rows}</div>
          <div>Open signals: {result.summary.signals_open_count}</div>
          <div>Open actions: {result.summary.actions_open_count ?? 0}</div>
        </div>
      )}

      <div style={{ marginTop: 24 }}>
        <h3>Plaid Pump (Dev)</h3>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <label>
            Start
            <input value={pumpStartDate} onChange={(e) => setPumpStartDate(e.target.value)} />
          </label>
          <label>
            End
            <input value={pumpEndDate} onChange={(e) => setPumpEndDate(e.target.value)} />
          </label>
          <label>
            Daily count
            <input
              type="number"
              value={dailyTxnCount}
              onChange={(e) => setDailyTxnCount(Number(e.target.value || 25))}
            />
          </label>
          <label>
            Profile
            <select value={profile} onChange={(e) => setProfile(e.target.value as any)}>
              <option value="mixed">mixed</option>
              <option value="retail">retail</option>
              <option value="services">services</option>
              <option value="ecom">ecom</option>
            </select>
          </label>
        </div>
        <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
          <button
            onClick={async () => {
              if (!selectedBusinessId) return;
              setError(null);
              try {
                await ensureDynamicPlaidItem(selectedBusinessId, false);
              } catch (e: any) {
                setError(e?.message ?? "Ensure dynamic item failed");
              }
            }}
            disabled={!selectedBusinessId}
          >
            Ensure Dynamic Item
          </button>
          <button
            onClick={async () => {
              if (!selectedBusinessId) return;
              setError(null);
              try {
                const payload = await pumpPlaidTransactions(selectedBusinessId, {
                  start_date: pumpStartDate,
                  end_date: pumpEndDate,
                  daily_txn_count: dailyTxnCount,
                  profile,
                  run_sync: true,
                  run_pipeline: true,
                  refresh_actions: true,
                });
                setPumpTelemetry(payload);
                bumpDataVersion();
              } catch (e: any) {
                setError(e?.message ?? "Pump failed");
              }
            }}
            disabled={!selectedBusinessId}
          >
            Pump Transactions
          </button>
        </div>
        {pumpTelemetry && (
          <pre style={{ marginTop: 8, background: "#f5f5f5", padding: 12 }}>
            {JSON.stringify(pumpTelemetry, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}
