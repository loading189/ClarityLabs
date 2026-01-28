import { useMemo, useState } from "react";
import { useMonthlyTrends } from "../../hooks/useMonthlyTrends";

function Chip({ label }: { label: string }) {
  return (
    <span
      style={{
        fontSize: 12,
        padding: "4px 8px",
        borderRadius: 999,
        border: "1px solid #e5e7eb",
        background: "#fafafa",
      }}
    >
      {label}
    </span>
  );
}

function formatMoney(x: number) {
  const sign = x < 0 ? "-" : "";
  const v = Math.abs(x);
  return `${sign}$${v.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function formatMonths(x: number | null | undefined) {
  if (x == null) return "—";
  if (!isFinite(x)) return "—";
  return `${x.toFixed(1)} mo`;
}

// ultra-lightweight SVG chart (no chart lib required)
function BandChart({
  series,
  band,
}: {
  series: Array<{ month: string; value: number }>;
  band: { lower: number; upper: number; center: number };
}) {
  const w = 900;
  const h = 220;
  const pad = 24;

  const ys = series.map((p) => p.value);

  const yMin = Math.min(...ys, band.lower);
  const yMax = Math.max(...ys, band.upper);
  const ySpan = yMax - yMin || 1;

  const xTo = (i: number) => pad + (i * (w - pad * 2)) / Math.max(1, series.length - 1);
  const yTo = (v: number) => pad + (h - pad * 2) * (1 - (v - yMin) / ySpan);

  const linePath = series
    .map((p, i) => `${i === 0 ? "M" : "L"} ${xTo(i).toFixed(1)} ${yTo(p.value).toFixed(1)}`)
    .join(" ");

  const bandTop = yTo(band.upper);
  const bandBot = yTo(band.lower);
  const bandY = Math.min(bandTop, bandBot);
  const bandH = Math.abs(bandBot - bandTop);

  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      style={{
        width: "100%",
        height: "auto",
        display: "block",
        borderRadius: 12,
        border: "1px solid #e5e7eb",
      }}
    >
      {/* band */}
      <rect x={pad} y={bandY} width={w - pad * 2} height={bandH} fill="rgba(0,0,0,0.06)" />
      {/* center line */}
      <line x1={pad} x2={w - pad} y1={yTo(band.center)} y2={yTo(band.center)} stroke="rgba(0,0,0,0.25)" />
      {/* value line */}
      <path d={linePath} fill="none" stroke="black" strokeWidth={2} />
      {/* last point */}
      {series.length > 0 && (
        <circle cx={xTo(series.length - 1)} cy={yTo(series[series.length - 1].value)} r={4} fill="black" />
      )}
    </svg>
  );
}

type MetricKey = "net" | "inflow" | "outflow" | "cash_end";

const METRICS: Array<{ key: MetricKey; label: string; subtitle: string }> = [
  { key: "net", label: "Net cash", subtitle: "inflow - outflow per month" },
  { key: "inflow", label: "Inflow", subtitle: "money in per month" },
  { key: "outflow", label: "Outflow", subtitle: "money out per month" },
  { key: "cash_end", label: "Cash balance", subtitle: "month-end cash balance" },
];

function statusToLabel(status: string) {
  return status === "below_band"
    ? "Below baseline (watch)"
    : status === "above_band"
    ? "Above baseline"
    : status === "in_band"
    ? "Within baseline"
    : "No data";
}

export default function TrendsTab({ businessId }: { businessId: string }) {
  const [lookbackMonths, setLookbackMonths] = useState(12);
  const [k, setK] = useState(2.0);
  const [metric, setMetric] = useState<MetricKey>("cash_end");

  const { data, loading, err, refresh } = useMonthlyTrends(businessId, lookbackMonths, k);

  const metricObj = (data?.metrics?.[metric] ?? null) as any;
  const series = useMemo(() => {
    const s = (metricObj?.series ?? []) as Array<any>;
    return s.map((r) => ({
      month: String(r.month),
      value: Number(r.value),
    }));
  }, [metricObj]);

  const band = metricObj?.band as any;
  const status = String(metricObj?.status ?? "no_data");
  const current = metricObj?.current as any;

  const cash = data?.cash as any;
  const burn = cash?.burn_rate_3m != null ? Number(cash.burn_rate_3m) : 0;
  const runway = cash?.runway_months != null ? Number(cash.runway_months) : null;
  const currentCash = cash?.current_cash != null ? Number(cash.current_cash) : null;

  const metricMeta = METRICS.find((m) => m.key === metric)!;

  return (
    <div style={{ paddingTop: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h3 style={{ marginTop: 0 }}>Trends</h3>
          <div style={{ fontSize: 12, opacity: 0.75 }}>
            {metricMeta.label}: {metricMeta.subtitle}. Baseline band uses median ± k·MAD.
          </div>
        </div>

        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <Chip label={statusToLabel(status)} />

          <label style={{ fontSize: 12, display: "flex", gap: 6, alignItems: "center" }}>
            Metric
            <select value={metric} onChange={(e) => setMetric(e.target.value as MetricKey)}>
              {METRICS.map((m) => (
                <option key={m.key} value={m.key}>
                  {m.label}
                </option>
              ))}
            </select>
          </label>

          <label style={{ fontSize: 12, display: "flex", gap: 6, alignItems: "center" }}>
            Lookback
            <select value={lookbackMonths} onChange={(e) => setLookbackMonths(Number(e.target.value))}>
              <option value={6}>6 mo</option>
              <option value={12}>12 mo</option>
              <option value={18}>18 mo</option>
              <option value={24}>24 mo</option>
            </select>
          </label>

          <label style={{ fontSize: 12, display: "flex", gap: 6, alignItems: "center" }}>
            Band (k)
            <select value={k} onChange={(e) => setK(Number(e.target.value))}>
              <option value={1.5}>1.5</option>
              <option value={2.0}>2.0</option>
              <option value={2.5}>2.5</option>
              <option value={3.0}>3.0</option>
            </select>
          </label>

          <button onClick={refresh} disabled={loading}>
            {loading ? "Loading…" : "Refresh"}
          </button>
        </div>
      </div>

      {err && <div style={{ marginTop: 10, color: "#b91c1c" }}>Error: {err}</div>}
      {loading && !data && <div style={{ marginTop: 10, opacity: 0.7 }}>Loading…</div>}

      {data && (
        <div style={{ marginTop: 12, display: "grid", gridTemplateColumns: "1fr", gap: 12 }}>
          {/* Chart */}
          {series.length > 1 && band && <BandChart series={series} band={band} />}

          {/* Summary cards */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 10 }}>
            <div style={{ border: "1px solid #e5e7eb", borderRadius: 12, padding: 12 }}>
              <div style={{ fontSize: 12, opacity: 0.75 }}>Current ({metricMeta.label})</div>
              <div style={{ fontSize: 22, fontWeight: 700 }}>
                {current ? formatMoney(Number(current.value)) : "—"}
              </div>
              <div style={{ fontSize: 12, opacity: 0.75, marginTop: 4 }}>{current?.month ?? ""}</div>
            </div>

            <div style={{ border: "1px solid #e5e7eb", borderRadius: 12, padding: 12 }}>
              <div style={{ fontSize: 12, opacity: 0.75 }}>Baseline center</div>
              <div style={{ fontSize: 22, fontWeight: 700 }}>{formatMoney(Number(band?.center ?? 0))}</div>
              <div style={{ fontSize: 12, opacity: 0.75, marginTop: 4 }}>
                Band: {formatMoney(Number(band?.lower ?? 0))} to {formatMoney(Number(band?.upper ?? 0))}
              </div>
            </div>

            <div style={{ border: "1px solid #e5e7eb", borderRadius: 12, padding: 12 }}>
              <div style={{ fontSize: 12, opacity: 0.75 }}>Burn & runway</div>
              <div style={{ fontSize: 14, fontWeight: 700 }}>
                Burn (3m): {burn > 0 ? formatMoney(burn) + "/mo" : "—"}
              </div>
              <div style={{ fontSize: 12, opacity: 0.75, marginTop: 6 }}>
                Runway: {formatMonths(runway)}
              </div>
              <div style={{ fontSize: 12, opacity: 0.75, marginTop: 6 }}>
                Current cash: {currentCash == null ? "—" : formatMoney(currentCash)}
              </div>
            </div>

            <div style={{ border: "1px solid #e5e7eb", borderRadius: 12, padding: 12 }}>
              <div style={{ fontSize: 12, opacity: 0.75 }}>Method</div>
              <div style={{ fontSize: 14, fontWeight: 700 }}>
                {String(data?.experiment?.band_method ?? "mad").toUpperCase()}
              </div>
              <div style={{ fontSize: 12, opacity: 0.75, marginTop: 6 }}>
                lookback {lookbackMonths} · k {k}
              </div>
            </div>
          </div>

          {/* Table (audit) */}
          <div style={{ border: "1px solid #e5e7eb", borderRadius: 12, overflow: "hidden" }}>
            <div style={{ padding: 10, fontSize: 12, background: "#fafafa", display: "flex", gap: 10 }}>
              <strong>Monthly series</strong>
              <span style={{ opacity: 0.7 }}>month / inflow / outflow / net / cash_end</span>
            </div>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr style={{ textAlign: "left", background: "#fafafa" }}>
                  <th style={{ padding: "8px 10px" }}>Month</th>
                  <th style={{ padding: "8px 10px", textAlign: "right" }}>Inflow</th>
                  <th style={{ padding: "8px 10px", textAlign: "right" }}>Outflow</th>
                  <th style={{ padding: "8px 10px", textAlign: "right" }}>Net</th>
                  <th style={{ padding: "8px 10px", textAlign: "right" }}>Cash end</th>
                </tr>
              </thead>
              <tbody>
                {(metricObj?.series ?? []).slice().reverse().map((r: any) => (
                  <tr key={r.month} style={{ borderTop: "1px solid #eee" }}>
                    <td style={{ padding: "8px 10px" }}>{r.month}</td>
                    <td style={{ padding: "8px 10px", textAlign: "right" }}>{formatMoney(Number(r.inflow))}</td>
                    <td style={{ padding: "8px 10px", textAlign: "right" }}>{formatMoney(Number(r.outflow))}</td>
                    <td style={{ padding: "8px 10px", textAlign: "right", fontWeight: 600 }}>
                      {formatMoney(Number(r.net))}
                    </td>
                    <td style={{ padding: "8px 10px", textAlign: "right", fontWeight: 600 }}>
                      {formatMoney(Number(r.cash_end))}
                    </td>
                  </tr>
                ))}
                {(metricObj?.series ?? []).length === 0 && (
                  <tr>
                    <td colSpan={5} style={{ padding: 10, opacity: 0.7 }}>
                      No monthly data.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
