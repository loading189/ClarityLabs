import { useEffect, useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";
import PageHeader from "../../components/common/PageHeader";
import FilterBar from "../../components/common/FilterBar";
import { ErrorState, LoadingState } from "../../components/common/DataState";
import { useFilters } from "../../app/filters/useFilters";
import { monthBounds, monthsBetween, resolveDateRange } from "../../app/filters/filters";
import { useDemoDateRange } from "../../app/filters/useDemoDateRange";
import { ledgerPath } from "../../app/routes/routeUtils";
import { useTrendsData } from "./useTrendsData";
import { useDemoDashboard } from "../../hooks/useDemoDashboard";
import { assertBusinessId } from "../../utils/businessId";
import { useAppState } from "../../app/state/appState";
import styles from "./TrendsPage.module.css";

type TrendRow = {
  month: string;
  inflow: number;
  outflow: number;
  net: number;
  cash_end: number;
};

function formatMoney(value: number) {
  return `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function LineChart({
  rows,
  onPointClick,
}: {
  rows: TrendRow[];
  onPointClick: (row: TrendRow) => void;
}) {
  const w = 520;
  const h = 180;
  const pad = 24;
  const values = rows.map((row) => row.cash_end);
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 1);
  const span = max - min || 1;

  const x = (i: number) => pad + (i * (w - pad * 2)) / Math.max(1, rows.length - 1);
  const y = (v: number) => pad + (h - pad * 2) * (1 - (v - min) / span);

  const path = rows
    .map((row, i) => `${i === 0 ? "M" : "L"} ${x(i).toFixed(1)} ${y(row.cash_end).toFixed(1)}`)
    .join(" ");

  return (
    <svg viewBox={`0 0 ${w} ${h}`} className={styles.chart}>
      <path d={path} className={styles.line} fill="none" strokeWidth={2} />
      {rows.map((row, i) => (
        <circle
          key={row.month}
          cx={x(i)}
          cy={y(row.cash_end)}
          r={4}
          className={styles.point}
          onClick={() => onPointClick(row)}
        />
      ))}
    </svg>
  );
}

function BarChart({
  rows,
  onBarClick,
}: {
  rows: TrendRow[];
  onBarClick: (row: TrendRow) => void;
}) {
  const w = 520;
  const h = 180;
  const pad = 24;
  const max = Math.max(...rows.map((row) => Math.max(row.inflow, row.outflow)), 1);

  return (
    <svg viewBox={`0 0 ${w} ${h}`} className={styles.chart}>
      {rows.map((row, i) => {
        const barWidth = (w - pad * 2) / rows.length - 8;
        const x = pad + i * ((w - pad * 2) / rows.length) + 4;
        const inflowHeight = (row.inflow / max) * (h - pad * 2);
        const outflowHeight = (row.outflow / max) * (h - pad * 2);
        return (
          <g key={row.month} onClick={() => onBarClick(row)}>
            <rect
              x={x}
              y={h - pad - inflowHeight}
              width={barWidth}
              height={inflowHeight}
              className={styles.barIn}
            />
            <rect
              x={x}
              y={h - pad - outflowHeight}
              width={barWidth}
              height={outflowHeight}
              className={styles.barOut}
              opacity={0.6}
            />
          </g>
        );
      })}
    </svg>
  );
}

export default function TrendsPage() {
  const { businessId: businessIdParam } = useParams();
  const businessId = assertBusinessId(businessIdParam, "TrendsPage");
  const navigate = useNavigate();
  const [filters, setFilters] = useFilters();
  const { data: dashboard } = useDemoDashboard();
  const { setDateRange } = useAppState();
  useDemoDateRange(filters, setFilters, dashboard?.metadata);
  const range = resolveDateRange(filters);
  useEffect(() => {
    setDateRange(range);
  }, [range.end, range.start, setDateRange]);
  const lookbackMonths = monthsBetween(range.start, range.end);
  const { data, loading, err } = useTrendsData(businessId, lookbackMonths, 2.0);

  const rows = useMemo(() => {
    const series = data?.analytics?.series ?? [];
    return series.map((row) => ({
      month: row.month,
      inflow: row.inflow.value,
      outflow: row.outflow.value,
      net: row.net.value,
      cash_end: row.cash_end.value,
    }));
  }, [data?.analytics?.series]);

  const filteredRows = useMemo(() => {
    const start = new Date(range.start);
    const end = new Date(range.end);
    return rows.filter((row) => {
      const bounds = monthBounds(row.month);
      if (!bounds) return false;
      const monthStart = new Date(bounds.start);
      const monthEnd = new Date(bounds.end);
      return monthEnd >= start && monthStart <= end;
    });
  }, [range.end, range.start, rows]);

  const handleDrilldown = (row: TrendRow) => {
    const bounds = monthBounds(row.month);
    if (!bounds) return;
    navigate(
      ledgerPath(businessId, {
        ...filters,
        start: bounds.start,
        end: bounds.end,
        window: undefined,
      })
    );
  };

  return (
    <div className={styles.page}>
      <PageHeader
        title="Trends"
        subtitle="Monthly rollups and time-series changes. Click any month to drill into the ledger."
      />

      <FilterBar filters={filters} onChange={setFilters} />

      {loading && <LoadingState label="Loading trend data…" />}
      {err && <ErrorState label={`Failed to load trends: ${err}`} />}

      {data && (
        <>
          <section className={styles.chartGrid}>
            <div className={styles.chartCard}>
              <div className={styles.chartTitle}>Cash end by month</div>
              <LineChart rows={filteredRows} onPointClick={handleDrilldown} />
            </div>
            <div className={styles.chartCard}>
              <div className={styles.chartTitle}>Inflow vs Outflow</div>
              <BarChart rows={filteredRows} onBarClick={handleDrilldown} />
            </div>
          </section>

          <section className={styles.tableCard}>
            <div className={styles.tableHeader}>
              <div>
                <h2>Monthly rollups</h2>
                <p>Each row drills into ledger transactions for that month.</p>
              </div>
              <div className={styles.tableMeta}>
                Range {range.start} → {range.end}
              </div>
            </div>
            <div className={styles.tableGrid}>
              <div className={styles.tableRowHeader}>
                <span>Month</span>
                <span>Inflow</span>
                <span>Outflow</span>
                <span>Net</span>
                <span>Cash end</span>
              </div>
              {filteredRows.map((row) => (
                <button
                  key={row.month}
                  type="button"
                  className={styles.tableRow}
                  onClick={() => handleDrilldown(row)}
                >
                  <span>{row.month}</span>
                  <span>{formatMoney(row.inflow)}</span>
                  <span>{formatMoney(row.outflow)}</span>
                  <span>{formatMoney(row.net)}</span>
                  <span>{formatMoney(row.cash_end)}</span>
                </button>
              ))}
              {filteredRows.length === 0 && (
                <div className={styles.empty}>No trend data in this window.</div>
              )}
            </div>
          </section>

          <section className={styles.categoryStub}>
            <div className={styles.sectionHeader}>
              <h2>Category totals over time</h2>
              <p>Coming next: drilldowns by category.</p>
            </div>
            <div className={styles.stubCard}>Category rollups will appear here.</div>
          </section>
        </>
      )}
    </div>
  );
}
