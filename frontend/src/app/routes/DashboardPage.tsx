import { useEffect } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import PageHeader from "../../components/common/PageHeader";
import FilterBar from "../../components/common/FilterBar";
import { ErrorState, LoadingState } from "../../components/common/DataState";
import { useDemoDashboard } from "../../hooks/useDemoDashboard";
import { useFilters } from "../filters/useFilters";
import { ledgerPath } from "./routeUtils";
import { monthBounds } from "../filters/filters";
import { useDemoDateRange } from "../filters/useDemoDateRange";
import { assertBusinessId } from "../../utils/businessId";
import styles from "./DashboardPage.module.css";
import { useAppState } from "../state/appState";
import NextActionsPanel from "../../features/actions/NextActionsPanel";

function formatMoney(value?: number | null) {
  if (value == null) return "—";
  return `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

export default function DashboardPage() {
  const { businessId: businessIdParam } = useParams();
  const businessId = assertBusinessId(businessIdParam, "DashboardPage");
  const navigate = useNavigate();
  const [filters, setFilters] = useFilters();
  const { data, loading, err } = useDemoDashboard();
  const { setDateRange } = useAppState();
  useDemoDateRange(filters, setFilters, data?.metadata);
  useEffect(() => {
    if (!filters.start || !filters.end) return;
    setDateRange({ start: filters.start, end: filters.end });
  }, [filters.end, filters.start, setDateRange]);

  const series = data?.analytics?.series ?? [];

  return (
    <div className={styles.page}>
      <PageHeader
        title="Dashboard"
        subtitle="Instrument panel for measurement and monitoring. Click any metric to drill into the ledger."
        actions={
          <Link className={styles.primaryButton} to={ledgerPath(businessId, filters)}>
            Open ledger
          </Link>
        }
      />

      <FilterBar filters={filters} onChange={setFilters} />

      <NextActionsPanel businessId={businessId} />

      <div className={styles.tableCard} style={{ marginBottom: 12 }}>
        Summary is now the primary workspace view. <Link to={`/app/${businessId}/summary`}>Open Summary</Link> for recent changes across signals and actions.
      </div>

      {loading && <LoadingState label="Loading dashboard metrics…" />}
      {err && <ErrorState label={`Failed to load dashboard: ${err}`} />}

      {data && (
        <>
          <section className={styles.kpiGrid}>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>Current cash</div>
              <div className={styles.kpiValue}>
                {formatMoney(data.kpis.current_cash.value)}
              </div>
              <div className={styles.kpiMeta}>As of {data.metadata.as_of}</div>
            </div>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>Inflow (30d)</div>
              <div className={styles.kpiValue}>
                {formatMoney(data.kpis.last_30d_inflow.value)}
              </div>
              <div className={styles.kpiMeta}>Monitoring only</div>
            </div>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>Outflow (30d)</div>
              <div className={styles.kpiValue}>
                {formatMoney(data.kpis.last_30d_outflow.value)}
              </div>
              <div className={styles.kpiMeta}>Monitoring only</div>
            </div>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>Net (30d)</div>
              <div className={styles.kpiValue}>
                {formatMoney(data.kpis.last_30d_net.value)}
              </div>
              <div className={styles.kpiMeta}>Monitoring only</div>
            </div>
          </section>

          <section className={styles.tableCard}>
            <div className={styles.tableHeader}>
              <div>
                <h2>Monthly rollup</h2>
                <p>Ledger-derived inflow/outflow and cash end. Click a month to drill down.</p>
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
              {series.map((row) => (
                <button
                  key={row.month}
                  className={styles.tableRow}
                  type="button"
                  onClick={() => {
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
                  }}
                >
                  <span>{row.month}</span>
                  <span>{formatMoney(row.inflow.value)}</span>
                  <span>{formatMoney(row.outflow.value)}</span>
                  <span>{formatMoney(row.net.value)}</span>
                  <span>{formatMoney(row.cash_end.value)}</span>
                </button>
              ))}
              {series.length === 0 && <div className={styles.empty}>No monthly data yet.</div>}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
