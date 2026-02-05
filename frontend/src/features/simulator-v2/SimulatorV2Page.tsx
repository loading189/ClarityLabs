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
  const [advanced, setAdvanced] = useState(false);
  const [result, setResult] = useState<SimSeedResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [anchorDate, setAnchorDate] = useState(todayIso());
  const [lookbackDays, setLookbackDays] = useState(120);
  const [forwardDays, setForwardDays] = useState(14);
  const [scenarioId, setScenarioId] = useState("cash_crunch");
  const [intensity, setIntensity] = useState(2);

  useEffect(() => {
    getSimV2Catalog().then(setCatalog).catch((e: Error) => setError(e.message));
  }, []);

  const runSeed = async (presetId?: string) => {
    setLoading(true);
    setError(null);
    try {
      const payload = advanced
        ? {
            business_id: businessId,
            scenarios: [{ id: scenarioId, intensity }],
            anchor_date: anchorDate,
            lookback_days: lookbackDays,
            forward_days: forwardDays,
            mode: "replace" as const,
          }
        : {
            business_id: businessId,
            preset_id: presetId,
            anchor_date: anchorDate,
            lookback_days: lookbackDays,
            forward_days: forwardDays,
            mode: "replace" as const,
          };
      const res = await seedSimV2(payload);
      setResult(res);
      bumpDataVersion();
    } catch (e: any) {
      setError(e?.message ?? "Seed failed");
    } finally {
      setLoading(false);
    }
  };

  const onReset = async () => {
    await resetSimV2(businessId);
    bumpDataVersion();
    setResult(null);
  };

  return (
    <div style={{ padding: 24 }}>
      <h2>Scenario-Driven Simulator v2</h2>
      <label>
        <input type="checkbox" checked={advanced} onChange={(e) => setAdvanced(e.target.checked)} /> Advanced
      </label>
      <div style={{ display: "flex", gap: 12, marginTop: 12 }}>
        <label>Anchor <input value={anchorDate} onChange={(e) => setAnchorDate(e.target.value)} /></label>
        <label>Lookback <input type="number" value={lookbackDays} onChange={(e) => setLookbackDays(Number(e.target.value))} /></label>
        <label>Forward <input type="number" value={forwardDays} onChange={(e) => setForwardDays(Number(e.target.value))} /></label>
      </div>

      {!advanced && (
        <div style={{ display: "grid", gap: 8, marginTop: 12 }}>
          {catalog?.presets?.map((p) => (
            <button key={p.id} onClick={() => runSeed(p.id)} disabled={loading}>
              Seed {p.title}
            </button>
          ))}
        </div>
      )}

      {advanced && (
        <div style={{ marginTop: 12 }}>
          <select value={scenarioId} onChange={(e) => setScenarioId(e.target.value)}>
            {catalog?.scenarios.map((s) => (
              <option value={s.id} key={s.id}>{s.title}</option>
            ))}
          </select>
          <input type="number" min={1} max={3} value={intensity} onChange={(e) => setIntensity(Number(e.target.value))} />
          <button onClick={() => runSeed()} disabled={loading}>Seed Scenario</button>
        </div>
      )}

      <button onClick={onReset} style={{ marginTop: 12 }}>Reset sim_v2 data</button>
      {error && <div style={{ color: "crimson" }}>{error}</div>}

      {result && (
        <div style={{ marginTop: 16 }}>
          <div>Window: {result.window.start_date} → {result.window.end_date}</div>
          <div>Events inserted: {result.stats.raw_events_inserted}</div>
          <div>Pulse ran: {String(result.stats.pulse_ran)}</div>
          <div>Signals produced: {result.signals.total}</div>
        </div>
      )}
    </div>
  );
}
