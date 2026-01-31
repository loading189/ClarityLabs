import { useEffect } from "react";
import { Link, useParams } from "react-router-dom";
import { useDemoDashboard } from "../../hooks/useDemoDashboard";
import { useBusinessDetailData } from "../../hooks/useBusinessDetailData";
import { useFilters } from "../filters/useFilters";
import { useDemoDateRange } from "../filters/useDemoDateRange";
import FilterBar from "../../components/common/FilterBar";
import PageHeader from "../../components/common/PageHeader";
import { ErrorState, LoadingState } from "../../components/common/DataState";
import { ledgerPath } from "./routeUtils";
import { assertBusinessId } from "../../utils/businessId";
import { useAppState } from "../state/appState";
import styles from "./HomePage.module.css";

function formatMoney(value?: number | null) {
  if (value == null) return "—";
  return `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

export default function HomePage() {
  const { businessId: businessIdParam } = useParams();
  const businessId = assertBusinessId(businessIdParam, "HomePage");
  const [filters, setFilters] = useFilters();
  const { data: dashboard, loading, err } = useDemoDashboard();
  const { data: detail } = useBusinessDetailData(businessId);
  const { setDateRange } = useAppState();
  useDemoDateRange(filters, setFilters, dashboard?.metadata);
  useEffect(() => {
    if (!filters.start || !filters.end) return;
    setDateRange({ start: filters.start, end: filters.end });
  }, [filters.end, filters.start, setDateRange]);

  const topSignals = (detail?.health_signals ?? []).slice(0, 4);
  const ledgerLink = ledgerPath(businessId, filters);

  return (
    <div className={styles.page}>
      <PageHeader
        title="Home"
        subtitle="Landing snapshot with key alerts and the fastest path to drilldown."
        actions={
          <div className={styles.headerActions}>
            <Link className={styles.primaryButton} to={ledgerLink}>
              Open ledger
            </Link>
            <Link className={styles.secondaryButton} to={`/app/${businessId}/health`}>
              View health
            </Link>
          </div>
        }
      />

      <FilterBar filters={filters} onChange={setFilters} />

      {loading && <LoadingState label="Loading business snapshot…" />}
      {err && <ErrorState label={`Failed to load snapshot: ${err}`} />}

      {!loading && !err && dashboard && (
        <>
          <section className={styles.kpiGrid}>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>Current cash</div>
              <div className={styles.kpiValue}>
                {formatMoney(dashboard.kpis.current_cash.value)}
              </div>
              <div className={styles.kpiMeta}>As of {dashboard.metadata.as_of}</div>
            </div>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>Last 30d inflow</div>
              <div className={styles.kpiValue}>
                {formatMoney(dashboard.kpis.last_30d_inflow.value)}
              </div>
              <div className={styles.kpiMeta}>Revenue velocity</div>
            </div>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>Last 30d outflow</div>
              <div className={styles.kpiValue}>
                {formatMoney(dashboard.kpis.last_30d_outflow.value)}
              </div>
              <div className={styles.kpiMeta}>Spend velocity</div>
            </div>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>Net movement</div>
              <div className={styles.kpiValue}>
                {formatMoney(dashboard.kpis.last_30d_net.value)}
              </div>
              <div className={styles.kpiMeta}>Monitoring only</div>
            </div>
          </section>

          <section className={styles.alerts}>
            <div className={styles.sectionHeader}>
              <div>
                <h2>Top alerts</h2>
                <p>Signals that require investigation and corrective action.</p>
              </div>
              <Link className={styles.link} to={`/app/${businessId}/health`}>
                Open full health view →
              </Link>
            </div>
            <div className={styles.alertGrid}>
              {topSignals.length === 0 && (
                <div className={styles.emptyCard}>No health alerts. Keep monitoring.</div>
              )}
              {topSignals.map((signal) => (
                <div key={signal.id} className={styles.alertCard}>
                  <div className={styles.alertSeverity}>{signal.severity.toUpperCase()}</div>
                  <div className={styles.alertTitle}>{signal.title}</div>
                  <div className={styles.alertMessage}>{signal.short_summary}</div>
                  <Link className={styles.link} to={`/app/${businessId}/health`}>
                    Investigate →
                  </Link>
                </div>
              ))}
            </div>
          </section>

          <section className={styles.ctaRow}>
            <Link className={styles.primaryButton} to={ledgerLink}>
              Drill into ledger
            </Link>
            <Link className={styles.secondaryButton} to={`/app/${businessId}/trends`}>
              Explore trends
            </Link>
          </section>
        </>
      )}
    </div>
  );
}
