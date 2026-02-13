import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getSimV2Catalog, resetSimV2, seedSimV2, type SimCatalog, type SimSeedResponse } from "../../api/simV2";
import { useAppState } from "../../app/state/appState";

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
    </div>
  );
}
