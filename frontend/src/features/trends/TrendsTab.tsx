import { useMemo, useState } from "react";
import { useMonthlyTrends } from "../../hooks/useMonthlyTrends";
import styles from "./TrendsTab.module.css";

function Chip({ label, className }: { label: string; className?: string }) {
  return <span className={`${styles.statusChip} ${className ?? ""}`}>{label}</span>;
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
      className={styles.chart}
    >
      {/* band */}
      <rect x={pad} y={bandY} width={w - pad * 2} height={bandH} className={styles.chartBand} />
      {/* center line */}
      <line x1={pad} x2={w - pad} y1={yTo(band.center)} y2={yTo(band.center)} className={styles.chartCenter} />
      {/* value line */}
      <path d={linePath} fill="none" strokeWidth={2} className={styles.chartLine} />
      {/* last point */}
      {series.length > 0 && (
        <circle cx={xTo(series.length - 1)} cy={yTo(series[series.length - 1].value)} r={4} className={styles.chartPoint} />
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
  const statusClass =
    status === "below_band"
      ? styles.statusChipWarning
      : status === "above_band"
      ? styles.statusChipPositive
      : status === "in_band"
      ? styles.statusChipNeutral
      : styles.statusChipMuted;

  return (
    <div className={styles.container}>
      <div className={styles.headerRow}>
        <div>
          <h3 className={styles.title}>Trends</h3>
          <div className={styles.subtitle}>
            {metricMeta.label}: {metricMeta.subtitle}. Baseline band uses median ± k·MAD.
          </div>
        </div>

        <div className={styles.controls}>
          <Chip label={statusToLabel(status)} className={statusClass} />

          <label className={styles.controlLabel}>
            Metric
            <select value={metric} onChange={(e) => setMetric(e.target.value as MetricKey)} className={styles.select}>
              {METRICS.map((m) => (
                <option key={m.key} value={m.key}>
                  {m.label}
                </option>
              ))}
            </select>
          </label>

          <label className={styles.controlLabel}>
            Lookback
            <select value={lookbackMonths} onChange={(e) => setLookbackMonths(Number(e.target.value))} className={styles.select}>
              <option value={6}>6 mo</option>
              <option value={12}>12 mo</option>
              <option value={18}>18 mo</option>
              <option value={24}>24 mo</option>
            </select>
          </label>

          <label className={styles.controlLabel}>
            Band (k)
            <select value={k} onChange={(e) => setK(Number(e.target.value))} className={styles.select}>
              <option value={1.5}>1.5</option>
              <option value={2.0}>2.0</option>
              <option value={2.5}>2.5</option>
              <option value={3.0}>3.0</option>
            </select>
          </label>

          <button onClick={refresh} disabled={loading} className={styles.button} type="button">
            {loading ? "Loading…" : "Refresh"}
          </button>
        </div>
      </div>

      {err && <div className={styles.error}>Error: {err}</div>}
      {loading && !data && <div className={styles.loading}>Loading…</div>}

      {data && (
        <div className={styles.content}>
          {/* Chart */}
          {series.length > 1 && band && <BandChart series={series} band={band} />}

          {/* Summary cards */}
          <div className={styles.summaryGrid}>
            <div className={styles.summaryCard}>
              <div className={styles.summaryLabel}>Current ({metricMeta.label})</div>
              <div className={styles.summaryValue}>{current ? formatMoney(Number(current.value)) : "—"}</div>
              <div className={styles.summaryMeta}>{current?.month ?? ""}</div>
            </div>

            <div className={styles.summaryCard}>
              <div className={styles.summaryLabel}>Baseline center</div>
              <div className={styles.summaryValue}>{formatMoney(Number(band?.center ?? 0))}</div>
              <div className={styles.summaryMeta}>
                Band: {formatMoney(Number(band?.lower ?? 0))} to {formatMoney(Number(band?.upper ?? 0))}
              </div>
            </div>

            <div className={styles.summaryCard}>
              <div className={styles.summaryLabel}>Burn & runway</div>
              <div className={styles.summaryStrong}>
                Burn (3m): {burn > 0 ? formatMoney(burn) + "/mo" : "—"}
              </div>
              <div className={styles.summaryMeta}>Runway: {formatMonths(runway)}</div>
              <div className={styles.summaryMeta}>
                Current cash: {currentCash == null ? "—" : formatMoney(currentCash)}
              </div>
            </div>

            <div className={styles.summaryCard}>
              <div className={styles.summaryLabel}>Method</div>
              <div className={styles.summaryStrong}>
                {String(data?.experiment?.band_method ?? "mad").toUpperCase()}
              </div>
              <div className={styles.summaryMeta}>
                lookback {lookbackMonths} · k {k}
              </div>
            </div>
          </div>

          {/* Table (audit) */}
          <div className={styles.tableCard}>
            <div className={styles.tableHeader}>
              <strong>Monthly series</strong>
              <span className={styles.subtitle}>month / inflow / outflow / net / cash_end</span>
            </div>
            <table className={styles.table}>
              <thead>
                <tr className={styles.tableHead}>
                  <th className={styles.tableCell}>Month</th>
                  <th className={`${styles.tableCell} ${styles.tableCellRight}`}>Inflow</th>
                  <th className={`${styles.tableCell} ${styles.tableCellRight}`}>Outflow</th>
                  <th className={`${styles.tableCell} ${styles.tableCellRight}`}>Net</th>
                  <th className={`${styles.tableCell} ${styles.tableCellRight}`}>Cash end</th>
                </tr>
              </thead>
              <tbody>
                {(metricObj?.series ?? []).slice().reverse().map((r: any) => (
                  <tr key={r.month}>
                    <td className={styles.tableCell}>{r.month}</td>
                    <td className={`${styles.tableCell} ${styles.tableCellRight}`}>{formatMoney(Number(r.inflow))}</td>
                    <td className={`${styles.tableCell} ${styles.tableCellRight}`}>{formatMoney(Number(r.outflow))}</td>
                    <td className={`${styles.tableCell} ${styles.tableCellRight} ${styles.tableCellStrong}`}>
                      {formatMoney(Number(r.net))}
                    </td>
                    <td className={`${styles.tableCell} ${styles.tableCellRight} ${styles.tableCellStrong}`}>
                      {formatMoney(Number(r.cash_end))}
                    </td>
                  </tr>
                ))}
                {(metricObj?.series ?? []).length === 0 && (
                  <tr>
                    <td colSpan={5} className={styles.emptyState}>
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
