import { useMemo, useState } from "react";
import { useLedger } from "../../hooks/useLedger";

function fmtMoney(n: number) {
  const sign = n < 0 ? "-" : "";
  const abs = Math.abs(n);
  return `${sign}$${abs.toFixed(2)}`;
}

function Chip({ label }: { label: string }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: "2px 8px",
        borderRadius: 999,
        background: "#f5f5f5",
        border: "1px solid #e9e9e9",
        fontSize: 12,
      }}
    >
      {label}
    </span>
  );
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
    <div style={{ border: "1px solid #e5e5e5", borderRadius: 10, padding: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
        <div style={{ fontWeight: 600 }}>{title}</div>
        {subtitle ? <small style={{ opacity: 0.7 }}>{subtitle}</small> : null}
      </div>
      <div style={{ marginTop: 10, fontSize: 22, fontWeight: 700 }}>{value}</div>
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

  if (loading && !lines) return <div style={{ padding: 12 }}>Loading ledger…</div>;
  if (err)
    return (
      <div style={{ padding: 12 }}>
        <div style={{ marginBottom: 8 }}>Error: {err}</div>
        <button onClick={refresh}>Retry</button>
      </div>
    );

  const rows = lines ?? [];

  return (
    <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 12 }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <div style={{ fontWeight: 600 }}>Ledger</div>

        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <small style={{ opacity: 0.75 }}>
            Range {start_date} → {end_date} · <span style={{ fontVariantNumeric: "tabular-nums" }}>{totals.count}</span>{" "}
            lines
          </small>

          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            style={{ padding: "6px 8px", borderRadius: 8, border: "1px solid #e5e5e5" }}
          >
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
            <option value={365}>Last 12 months</option>
          </select>

          <button onClick={refresh}>Refresh</button>
        </div>
      </div>

      {/* Summary cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 12 }}>
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
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 12 }}>
        <div style={{ border: "1px solid #e5e5e5", borderRadius: 10, padding: 12 }}>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>Income Statement</div>
          {incomeStatement ? (
            <>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <small style={{ opacity: 0.75 }}>Revenue</small>
                <div style={{ fontVariantNumeric: "tabular-nums" }}>{fmtMoney(incomeStatement.revenue_total)}</div>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <small style={{ opacity: 0.75 }}>Expenses</small>
                <div style={{ fontVariantNumeric: "tabular-nums" }}>{fmtMoney(-incomeStatement.expense_total)}</div>
              </div>
              <div style={{ height: 8 }} />
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <small style={{ opacity: 0.75 }}>Net Income</small>
                <div style={{ fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
                  {fmtMoney(incomeStatement.net_income)}
                </div>
              </div>
            </>
          ) : (
            <small style={{ opacity: 0.75 }}>Not available yet.</small>
          )}
        </div>

        <div style={{ border: "1px solid #e5e5e5", borderRadius: 10, padding: 12 }}>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>Cash Flow</div>
          {cashFlow ? (
            <>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <small style={{ opacity: 0.75 }}>Cash In</small>
                <div style={{ fontVariantNumeric: "tabular-nums" }}>{fmtMoney(cashFlow.cash_in)}</div>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <small style={{ opacity: 0.75 }}>Cash Out</small>
                <div style={{ fontVariantNumeric: "tabular-nums" }}>{fmtMoney(-cashFlow.cash_out)}</div>
              </div>
              <div style={{ height: 8 }} />
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <small style={{ opacity: 0.75 }}>Net</small>
                <div style={{ fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
                  {fmtMoney(cashFlow.net_cash_flow)}
                </div>
              </div>
            </>
          ) : (
            <small style={{ opacity: 0.75 }}>Not available yet.</small>
          )}
        </div>

        <div style={{ border: "1px solid #e5e5e5", borderRadius: 10, padding: 12 }}>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>Balance Sheet (V1)</div>
          {balanceSheet ? (
            <>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <small style={{ opacity: 0.75 }}>Assets</small>
                <div style={{ fontVariantNumeric: "tabular-nums" }}>{fmtMoney(balanceSheet.assets_total)}</div>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <small style={{ opacity: 0.75 }}>Liabilities</small>
                <div style={{ fontVariantNumeric: "tabular-nums" }}>{fmtMoney(balanceSheet.liabilities_total)}</div>
              </div>
              <div style={{ height: 8 }} />
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <small style={{ opacity: 0.75 }}>Equity</small>
                <div style={{ fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
                  {fmtMoney(balanceSheet.equity_total)}
                </div>
              </div>
            </>
          ) : (
            <small style={{ opacity: 0.75 }}>Not available yet.</small>
          )}
        </div>
      </div>

      {/* Ledger table */}
      <div style={{ border: "1px solid #e5e5e5", borderRadius: 8, overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ textAlign: "left", background: "#fafafa" }}>
              <th style={{ padding: "10px 12px" }}>When</th>
              <th style={{ padding: "10px 12px" }}>Description</th>
              <th style={{ padding: "10px 12px" }}>Account</th>
              <th style={{ padding: "10px 12px" }}>Category</th>
              <th style={{ padding: "10px 12px" }}>Type</th>
              <th style={{ padding: "10px 12px", textAlign: "right" }}>Amount</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((l) => (
              <tr key={l.source_event_id} style={{ borderTop: "1px solid #eee" }}>
                <td style={{ padding: "10px 12px", whiteSpace: "nowrap" }}>
                  {new Date(l.occurred_at).toLocaleString()}
                </td>

                <td style={{ padding: "10px 12px" }}>
                  <div style={{ fontWeight: 500 }}>{l.description}</div>
                  <small style={{ opacity: 0.75 }}>
                    event {l.source_event_id.slice(-6)} · <Chip label={l.direction} />
                  </small>
                </td>

                <td style={{ padding: "10px 12px" }}>{l.account_name}</td>
                <td style={{ padding: "10px 12px" }}>{l.category_name}</td>

                <td style={{ padding: "10px 12px" }}>
                  <small style={{ opacity: 0.85 }}>
                    {l.account_type}
                    {l.account_subtype ? ` · ${l.account_subtype}` : ""}
                  </small>
                </td>

                <td style={{ padding: "10px 12px", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                  {fmtMoney(l.signed_amount)}
                </td>
              </tr>
            ))}

            {rows.length === 0 && (
              <tr>
                <td colSpan={6} style={{ padding: 12, opacity: 0.75 }}>
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
