import { useEffect, useMemo, useState } from "react";
import { computeLedgerSummary, computeRunningBalance } from "../../analytics/core";
import { useLedger } from "../../hooks/useLedger";
import { useAppState } from "../../app/state/appState";
import styles from "./LedgerTab.module.css";

export type LedgerDrilldown = {
  direction?: "inflow" | "outflow";
  date_preset?: "30d" | "90d" | "365d";
  search?: string;
};

function formatMoney(value: number) {
  // Avoid "-$0.00" and improve readability with grouping.
  const normalized = Math.abs(value) < 0.005 ? 0 : value;
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(normalized);
}

function isoLocalDate(d: Date) {
  // Produces YYYY-MM-DD in *local* time without timezone surprises.
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function rangeLastNDays(days: number) {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - days);
  return { start: isoLocalDate(start), end: isoLocalDate(end) };
}

function Chip({
  label,
  tone = "neutral",
}: {
  label: string;
  tone?: "neutral" | "success" | "danger";
}) {
  const cls =
    tone === "success"
      ? styles.chipSuccess
      : tone === "danger"
      ? styles.chipDanger
      : styles.chip;
  return <span className={cls}>{label}</span>;
}

function StatCard({
  title,
  value,
  subtitle,
}: {
  title: string;
  value: string;
  subtitle?: string;
}) {
  return (
    <div className={styles.statCard}>
      <div className={styles.statHeader}>
        <div className={styles.statTitle}>{title}</div>
        {subtitle ? <small className={styles.statSubtitle}>{subtitle}</small> : null}
      </div>
      <div className={styles.statValue}>{value}</div>
    </div>
  );
}

function presetToDays(preset?: LedgerDrilldown["date_preset"]) {
  if (preset === "365d") return 365;
  if (preset === "90d") return 90;
  return 30;
}

export function LedgerTab({
  drilldown,
  refreshToken,
  onClearDrilldown,
}: {
  drilldown?: LedgerDrilldown | null;
  refreshToken?: number;
  onClearDrilldown?: () => void;
}) {
  const [days, setDays] = useState(30);
  const { setDateRange } = useAppState();

  const {
    lines,
    incomeStatement,
    cashFlow,
    balanceSheet,
    loading,
    err,
    refresh,
    start_date,
    end_date,
  } = useLedger({ limit: 1000 });

  // Sync days preset from drilldown (Health → Ledger deep link)
  useEffect(() => {
    if (!drilldown?.date_preset) {
      setDays(30);
      return;
    }
    setDays(presetToDays(drilldown.date_preset));
  }, [drilldown?.date_preset]);

  // Push date range into global app state (so other tabs stay aligned)
  useEffect(() => {
    setDateRange(rangeLastNDays(days));
  }, [days, setDateRange]);

  // Refresh when refreshToken changes (not when it's merely truthy)
  useEffect(() => {
    if (refreshToken == null) return;
    refresh();
  }, [refreshToken, refresh]);

  const drilldownSummary = useMemo(() => {
    if (!drilldown) return "";
    const parts: string[] = [];
    if (drilldown.direction) parts.push(`Direction: ${drilldown.direction}`);
    if (drilldown.search) parts.push(`Search: "${drilldown.search}"`);
    if (drilldown.date_preset) parts.push(`Range: ${drilldown.date_preset}`);
    return parts.join(" · ");
  }, [drilldown]);

  const dateFormatter = useMemo(
    () =>
      new Intl.DateTimeFormat(undefined, {
        month: "short",
        day: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }),
    []
  );

  // IMPORTANT: enforce deterministic sort before computing running balances
  const baseRows = useMemo(() => {
    const arr = lines ?? [];
    // Sort ascending by occurred_at so running balance is meaningful left-to-right.
    return [...arr].sort(
      (a, b) => new Date(a.occurred_at).getTime() - new Date(b.occurred_at).getTime()
    );
  }, [lines]);

  const filteredRows = useMemo(() => {
    if (!drilldown) return baseRows;

    const search = (drilldown.search ?? "").trim().toLowerCase();

    return baseRows.filter((row) => {
      if (drilldown.direction && row.direction !== drilldown.direction) return false;

      if (search) {
        const haystack = `${row.description ?? ""} ${row.category_name ?? ""}`.toLowerCase();
        if (!haystack.includes(search)) return false;
      }
      return true;
    });
  }, [baseRows, drilldown]);

  const totals = useMemo(() => computeLedgerSummary(filteredRows), [filteredRows]);
  const runningBalanceById = useMemo(() => computeRunningBalance(filteredRows), [filteredRows]);

  // Render states
  if (loading && !lines) return <div className={styles.loadingState}>Loading ledger…</div>;

  if (err) {
    return (
      <div className={styles.errorState}>
        <div className={styles.errorMessage}>Error: {err}</div>
        <button onClick={refresh} className={styles.button} type="button">
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      {/* Header */}
      <div className={styles.headerRow}>
        <div className={styles.title}>Ledger</div>

        <div className={styles.controls}>
          <small className={styles.meta}>
            Range {start_date} → {end_date} ·{" "}
            <span className={styles.tabularNums}>{totals.count}</span> lines
          </small>

          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className={styles.select}
          >
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
            <option value={365}>Last 12 months</option>
          </select>

          <button
            onClick={refresh}
            className={styles.button}
            type="button"
            disabled={loading}
            aria-disabled={loading}
          >
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </div>

      {drilldown && (
        <div className={styles.drilldownBanner}>
          <span className={styles.drilldownLabel}>Active drilldown</span>
          <span className={styles.drilldownText}>
            {drilldownSummary || "Filters applied from Health."}
          </span>
          <button
            className={styles.drilldownClear}
            onClick={() => onClearDrilldown?.()}
            type="button"
          >
            Clear
          </button>
        </div>
      )}

      {/* Summary cards */}
      <div className={styles.summaryGrid}>
        <StatCard title="Cash In" value={formatMoney(totals.inflow.value)} subtitle="Posted lines" />
        <StatCard
          title="Cash Out"
          value={formatMoney(-totals.outflow.value)}
          subtitle="Posted lines"
        />
        <StatCard title="Net Cash Flow" value={formatMoney(totals.net.value)} subtitle="Posted lines" />
        <StatCard
          title="Balance Sheet (MVP)"
          value={balanceSheet ? formatMoney(balanceSheet.cash) : "—"}
          subtitle={balanceSheet ? `as of ${balanceSheet.as_of}` : "not available"}
        />
      </div>

      {/* Statements (compact) */}
      <div className={styles.statementsGrid}>
        <div className={styles.statementCard}>
          <div className={styles.statementTitle}>Income Statement</div>
          {incomeStatement ? (
            <>
              <div className={styles.statementRow}>
                <small>Revenue</small>
                <div className={styles.statementValue}>
                  {formatMoney(incomeStatement.revenue_total)}
                </div>
              </div>
              <div className={styles.statementRow}>
                <small>Expenses</small>
                <div className={styles.statementValue}>
                  {formatMoney(-incomeStatement.expense_total)}
                </div>
              </div>
              <div className={styles.statementRow}>
                <small>Net Income</small>
                <div className={styles.statementValueStrong}>
                  {formatMoney(incomeStatement.net_income)}
                </div>
              </div>
            </>
          ) : (
            <small className={styles.meta}>Not available yet.</small>
          )}
        </div>

        <div className={styles.statementCard}>
          <div className={styles.statementTitle}>Cash Flow</div>
          {cashFlow ? (
            <>
              <div className={styles.statementRow}>
                <small>Cash In</small>
                <div className={styles.statementValue}>{formatMoney(cashFlow.cash_in)}</div>
              </div>
              <div className={styles.statementRow}>
                <small>Cash Out</small>
                <div className={styles.statementValue}>{formatMoney(-cashFlow.cash_out)}</div>
              </div>
              <div className={styles.statementRow}>
                <small>Net</small>
                <div className={styles.statementValueStrong}>
                  {formatMoney(cashFlow.net_cash_flow)}
                </div>
              </div>
            </>
          ) : (
            <small className={styles.meta}>Not available yet.</small>
          )}
        </div>

        <div className={styles.statementCard}>
          <div className={styles.statementTitle}>Balance Sheet (V1)</div>
          {balanceSheet ? (
            <>
              <div className={styles.statementRow}>
                <small>Assets</small>
                <div className={styles.statementValue}>
                  {formatMoney(balanceSheet.assets_total)}
                </div>
              </div>
              <div className={styles.statementRow}>
                <small>Liabilities</small>
                <div className={styles.statementValue}>
                  {formatMoney(balanceSheet.liabilities_total)}
                </div>
              </div>
              <div className={styles.statementRow}>
                <small>Equity</small>
                <div className={styles.statementValueStrong}>
                  {formatMoney(balanceSheet.equity_total)}
                </div>
              </div>
            </>
          ) : (
            <small className={styles.meta}>Not available yet.</small>
          )}
        </div>
      </div>

      {/* Ledger table */}
      <div className={styles.tableCard}>
        <table className={styles.table}>
          <thead>
            <tr className={styles.tableHeadRow}>
              <th className={styles.tableHeadCell}>When</th>
              <th className={styles.tableHeadCell}>Description</th>
              <th className={styles.tableHeadCell}>Account</th>
              <th className={styles.tableHeadCell}>Category</th>
              <th className={styles.tableHeadCell}>Type</th>
              <th className={`${styles.tableHeadCell} ${styles.tableCellRight}`}>Amount</th>
              <th className={`${styles.tableHeadCell} ${styles.tableCellRight}`}>Balance (range)</th>
            </tr>
          </thead>

          <tbody>
            {filteredRows.map((l) => {
              const chipTone = l.direction === "inflow" ? "success" : "danger";
              return (
                <tr key={l.source_event_id} className={styles.tableRow}>
                  <td className={`${styles.tableCell} ${styles.tableCellNoWrap}`}>
                    {dateFormatter.format(new Date(l.occurred_at))}
                  </td>

                  <td className={styles.tableCell}>
                    <div className={styles.tableTitle}>{l.description ?? "—"}</div>
                    <small className={styles.tableSub}>
                      event {l.source_event_id.slice(-6)} ·{" "}
                      <Chip label={l.direction} tone={chipTone} />
                    </small>
                  </td>

                  <td className={styles.tableCell}>{l.account_name ?? "—"}</td>
                  <td className={styles.tableCell}>{l.category_name ?? "Needs review"}</td>

                  <td className={styles.tableCell}>
                    <small className={styles.meta}>
                      {l.account_type}
                      {l.account_subtype ? ` · ${l.account_subtype}` : ""}
                    </small>
                  </td>

                  <td className={`${styles.tableCell} ${styles.tableCellRight}`}>
                    {formatMoney(l.signed_amount)}
                  </td>

                  <td className={`${styles.tableCell} ${styles.tableCellRight} ${styles.balanceCell}`}>
                    {formatMoney(runningBalanceById.get(l.source_event_id) ?? 0)}
                  </td>
                </tr>
              );
            })}

            {filteredRows.length === 0 && (
              <tr>
                <td colSpan={7} className={styles.emptyState}>
                  {lines && lines.length > 0
                    ? "No ledger lines match the current drilldown."
                    : "No ledger lines found in this date range."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
