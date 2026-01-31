import { useEffect, useMemo, useRef, useState } from "react";
import { fetchCategoryDrilldown, fetchVendorDrilldown } from "../../api/demo";
import { useDemoDashboard } from "../../hooks/useDemoDashboard";
import type { CategorizeDrilldown } from "../categorize";
import type { DashboardSignal, DrilldownResponse } from "../../types";
import styles from "./DashboardTab.module.css";

function formatMoney(value: number) {
  const sign = value < 0 ? "-" : "";
  const abs = Math.abs(value);
  return `${sign}$${abs.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function formatSigned(value: number) {
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  const abs = Math.abs(value);
  return `${sign}$${abs.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function kpiLabel(label: string, value: number) {
  return (
    <div className={styles.kpiCard}>
      <div className={styles.kpiLabel}>{label}</div>
      <div className={styles.kpiValue}>{formatMoney(value)}</div>
    </div>
  );
}

function signalLabel(severity: string) {
  if (severity === "red") return styles.signalRed;
  if (severity === "yellow") return styles.signalYellow;
  return styles.signalGreen;
}

export default function DashboardTab({
  businessId,
  onNavigate,
}: {
  businessId: string;
  onNavigate?: (target: "categorize", drilldown?: CategorizeDrilldown | null) => void;
}) {
  const { data, loading, err, refresh } = useDemoDashboard();
  const signals = data?.signals ?? [];

  const [selectedKey, setSelectedKey] = useState<string | null>(signals[0]?.key ?? null);
  const selectedSignal = useMemo(() => {
    if (!signals.length) return null;
    return signals.find((s) => s.key === selectedKey) ?? signals[0] ?? null;
  }, [signals, selectedKey]);

  useEffect(() => {
    setSelectedKey(signals[0]?.key ?? null);
  }, [businessId, signals]);

  const [offset, setOffset] = useState(0);
  const [limit] = useState(12);
  const [drilldown, setDrilldown] = useState<DrilldownResponse | null>(null);
  const [drilldownErr, setDrilldownErr] = useState<string | null>(null);
  const [drilldownLoading, setDrilldownLoading] = useState(false);
  const drilldownSeq = useRef(0);

  const currentDrilldown = selectedSignal?.drilldown ?? null;

  useEffect(() => {
    setOffset(0);
  }, [selectedSignal?.key]);

  useEffect(() => {
    async function load() {
      if (!currentDrilldown || !selectedSignal) {
        setDrilldown(null);
        return;
      }
      const seq = (drilldownSeq.current += 1);
      setDrilldownLoading(true);
      setDrilldownErr(null);
      try {
        const { kind, value, window_days } = currentDrilldown;
        const data = await (kind === "vendor"
          ? fetchVendorDrilldown(businessId, value, window_days, limit, offset)
          : fetchCategoryDrilldown(businessId, value, window_days, limit, offset));
        if (seq !== drilldownSeq.current) return;
        setDrilldown(data);
      } catch (e: any) {
        if (seq !== drilldownSeq.current) return;
        setDrilldownErr(e?.message ?? "Failed to load drilldown");
      } finally {
        if (seq === drilldownSeq.current) {
          setDrilldownLoading(false);
        }
      }
    }

    load();
  }, [businessId, currentDrilldown, limit, offset, selectedSignal]);

  const trendSeries = useMemo(() => {
    const series = data?.analytics?.series ?? [];
    return series.slice(-6);
  }, [data?.analytics]);

  const total = drilldown?.total ?? 0;
  const rowStart = total === 0 ? 0 : offset + 1;
  const rowEnd = Math.min(total, offset + limit);

  const showFixCTA =
    currentDrilldown?.kind === "category" &&
    (currentDrilldown.value ?? "").toLowerCase() === "uncategorized";

  const handleFixCTA = () => {
    onNavigate?.("categorize", {
      direction: "outflow",
      date_preset: "30d",
    });
  };

  return (
    <div className={styles.container}>
      <div className={styles.headerRow}>
        <div>
          <h3 className={styles.title}>Dashboard</h3>
          <div className={styles.subtitle}>Signals and evidence for the selected business.</div>
        </div>
        <button className={styles.refreshButton} type="button" onClick={refresh}>
          Refresh
        </button>
      </div>

      {loading && <div className={styles.status}>Loading dashboard…</div>}
      {err && <div className={styles.error}>Error: {err}</div>}

      {!loading && !err && data && (
        <>
          <section className={styles.kpiGrid}>
            {kpiLabel("Current cash", data.kpis.current_cash.value)}
            {kpiLabel("Last 30d inflow", data.kpis.last_30d_inflow.value)}
            {kpiLabel("Last 30d outflow", data.kpis.last_30d_outflow.value)}
            {kpiLabel("Last 30d net", data.kpis.last_30d_net.value)}
          </section>

          <section className={styles.trendsSection}>
            <div className={styles.sectionHeader}>
              <h4>Monthly trends (last 6 months)</h4>
              <span className={styles.sectionSub}>
                Net, inflow, outflow, and cash-end. Values are ledger-derived.
              </span>
            </div>
            <div className={styles.trendsTable}>
              <div className={styles.trendsRowHeader}>
                <span>Month</span>
                <span>Inflow</span>
                <span>Outflow</span>
                <span>Net</span>
                <span>Cash end</span>
              </div>
              {trendSeries.map((row) => (
                <div key={row.month} className={styles.trendsRow}>
                  <span>{row.month}</span>
                  <span>{formatMoney(Number(row.inflow?.value || 0))}</span>
                  <span>{formatMoney(Number(row.outflow?.value || 0))}</span>
                  <span>{formatSigned(Number(row.net?.value || 0))}</span>
                  <span>{formatMoney(Number(row.cash_end?.value || 0))}</span>
                </div>
              ))}
              {!trendSeries.length && <div className={styles.empty}>No trend data.</div>}
            </div>
          </section>

          <div className={styles.contentGrid}>
            <section className={styles.signalsSection}>
              <div className={styles.sectionHeader}>
                <h4>Signals</h4>
                <span className={styles.sectionSub}>Sorted by priority. Click to view evidence.</span>
              </div>
              <div className={styles.signalsList}>
                {signals.map((signal: DashboardSignal) => (
                  <button
                    key={signal.key}
                    type="button"
                    className={`${styles.signalCard} ${
                      selectedSignal?.key === signal.key ? styles.signalCardActive : ""
                    }`}
                    onClick={() => setSelectedKey(signal.key)}
                  >
                    <div className={`${styles.signalSeverity} ${signalLabel(signal.severity)}`} />
                    <div>
                      <div className={styles.signalTitle}>{signal.title}</div>
                      <div className={styles.signalMessage}>{signal.message}</div>
                    </div>
                  </button>
                ))}
                {!signals.length && <div className={styles.empty}>No signals yet.</div>}
              </div>
            </section>

            <aside className={styles.drawer}>
              <div className={styles.sectionHeader}>
                <h4>Signal drilldown</h4>
                <span className={styles.sectionSub}>
                  {selectedSignal?.title ?? "Select a signal to view evidence."}
                </span>
              </div>

              {!selectedSignal && <div className={styles.empty}>No signal selected.</div>}

              {selectedSignal && !currentDrilldown && (
                <div className={styles.empty}>No drilldown available for this signal.</div>
              )}

              {selectedSignal && currentDrilldown && (
                <>
                  <div className={styles.drawerMeta}>
                    <span>
                      {currentDrilldown.kind === "vendor" ? "Vendor" : "Category"}:{" "}
                      <strong>{currentDrilldown.label ?? currentDrilldown.value}</strong>
                    </span>
                    <span>{currentDrilldown.window_days}d window</span>
                  </div>

                  {showFixCTA && (
                    <button className={styles.ctaButton} type="button" onClick={handleFixCTA}>
                      Fix in Categorize
                    </button>
                  )}

                  {drilldownLoading && <div className={styles.status}>Loading drilldown…</div>}
                  {drilldownErr && <div className={styles.error}>Error: {drilldownErr}</div>}

                  {!drilldownLoading && !drilldownErr && (
                    <>
                      <div className={styles.drawerTable}>
                        <div className={styles.drawerRowHeader}>
                          <span>Date</span>
                          <span>Description</span>
                          <span>Category</span>
                          <span>Amount</span>
                        </div>
                        {drilldown?.rows.map((row) => (
                          <div key={row.source_event_id} className={styles.drawerRow}>
                            <span>{row.date}</span>
                            <span className={styles.drawerDescription}>{row.description}</span>
                            <span>{row.category}</span>
                            <span>{formatSigned(Number(row.amount || 0))}</span>
                          </div>
                        ))}
                        {!drilldown?.rows?.length && (
                          <div className={styles.empty}>No transactions in this window.</div>
                        )}
                      </div>

                      <div className={styles.pagination}>
                        <span>
                          {rowStart}-{rowEnd} of {total}
                        </span>
                        <div className={styles.paginationButtons}>
                          <button
                            type="button"
                            className={styles.pageButton}
                            onClick={() => setOffset(Math.max(0, offset - limit))}
                            disabled={offset === 0}
                          >
                            Prev
                          </button>
                          <button
                            type="button"
                            className={styles.pageButton}
                            onClick={() => setOffset(offset + limit)}
                            disabled={offset + limit >= total}
                          >
                            Next
                          </button>
                        </div>
                      </div>
                    </>
                  )}
                </>
              )}
            </aside>
          </div>
        </>
      )}
    </div>
  );
}
