import { useMemo, useState } from "react";
import { useLedger } from "../../hooks/useLedger";
import styles from "./LedgerTab.module.css";

function fmtMoney(n: number) {
  const sign = n < 0 ? "-" : "";
  const abs = Math.abs(n);
  return `${sign}$${abs.toFixed(2)}`;
}

function Chip({ label }: { label: string }) {
  return <span className={styles.chip}>{label}</span>;
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

export function LedgerTab({ businessId }: { businessId: string }) {
  const [days, setDays] = useState(30);
  const { lines, incomeStatement, cashFlow, balanceSheet, loading, err, refresh, start_date, end_date } =
    useLedger(businessId, { days, limit: 1000 });

  const totals = useMemo(() => {
    const arr = lines ?? [];
    let inflow = 0;
    let outflow = 0;
    for (const l of arr) {
      if (l.signed_amount >= 0) inflow += l.signed_amount;
      else outflow += Math.abs(l.signed_amount);
    }
    return { inflow, outflow, net: inflow - outflow, count: arr.length };
  }, [lines]);

  if (loading && !lines) return <div className={styles.loadingState}>Loading ledger…</div>;
  if (err)
    return (
      <div className={styles.errorState}>
        <div className={styles.errorMessage}>Error: {err}</div>
        <button onClick={refresh} className={styles.button} type="button">
          Retry
        </button>
      </div>
    );

  const rows = lines ?? [];

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

          <button onClick={refresh} className={styles.button} type="button">
            Refresh
          </button>
        </div>
      </div>

      {/* Summary cards */}
      <div className={styles.summaryGrid}>
        <StatCard title="Cash In" value={fmtMoney(totals.inflow)} subtitle="Posted lines" />
        <StatCard title="Cash Out" value={fmtMoney(-totals.outflow)} subtitle="Posted lines" />
        <StatCard title="Net Cash Flow" value={fmtMoney(totals.net)} subtitle="Posted lines" />
        <StatCard
          title="Balance Sheet (MVP)"
          value={balanceSheet ? fmtMoney(balanceSheet.cash) : "—"}
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
                <div className={styles.statementValue}>{fmtMoney(incomeStatement.revenue_total)}</div>
              </div>
              <div className={styles.statementRow}>
                <small>Expenses</small>
                <div className={styles.statementValue}>{fmtMoney(-incomeStatement.expense_total)}</div>
              </div>
              <div className={styles.statementRow}>
                <small>Net Income</small>
                <div className={styles.statementValueStrong}>{fmtMoney(incomeStatement.net_income)}</div>
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
                <div className={styles.statementValue}>{fmtMoney(cashFlow.cash_in)}</div>
              </div>
              <div className={styles.statementRow}>
                <small>Cash Out</small>
                <div className={styles.statementValue}>{fmtMoney(-cashFlow.cash_out)}</div>
              </div>
              <div className={styles.statementRow}>
                <small>Net</small>
                <div className={styles.statementValueStrong}>{fmtMoney(cashFlow.net_cash_flow)}</div>
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
                <div className={styles.statementValue}>{fmtMoney(balanceSheet.assets_total)}</div>
              </div>
              <div className={styles.statementRow}>
                <small>Liabilities</small>
                <div className={styles.statementValue}>{fmtMoney(balanceSheet.liabilities_total)}</div>
              </div>
              <div className={styles.statementRow}>
                <small>Equity</small>
                <div className={styles.statementValueStrong}>{fmtMoney(balanceSheet.equity_total)}</div>
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
            <tr className={styles.tableHead}>
              <th className={styles.tableCell}>When</th>
              <th className={styles.tableCell}>Description</th>
              <th className={styles.tableCell}>Account</th>
              <th className={styles.tableCell}>Category</th>
              <th className={styles.tableCell}>Type</th>
              <th className={`${styles.tableCell} ${styles.tableCellRight}`}>Amount</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((l) => (
              <tr key={l.source_event_id}>
                <td className={`${styles.tableCell} ${styles.tableCellNoWrap}`}>
                  {new Date(l.occurred_at).toLocaleString()}
                </td>

                <td className={styles.tableCell}>
                  <div className={styles.tableTitle}>{l.description}</div>
                  <small className={styles.tableSub}>
                    event {l.source_event_id.slice(-6)} · <Chip label={l.direction} />
                  </small>
                </td>

                <td className={styles.tableCell}>{l.account_name}</td>
                <td className={styles.tableCell}>{l.category_name}</td>

                <td className={styles.tableCell}>
                  <small className={styles.meta}>
                    {l.account_type}
                    {l.account_subtype ? ` · ${l.account_subtype}` : ""}
                  </small>
                </td>

                <td className={`${styles.tableCell} ${styles.tableCellRight}`}>
                  {fmtMoney(l.signed_amount)}
                </td>
              </tr>
            ))}

            {rows.length === 0 && (
              <tr>
                <td colSpan={6} className={styles.emptyState}>
                  No posted ledger lines yet. Categorize a few transactions first.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
