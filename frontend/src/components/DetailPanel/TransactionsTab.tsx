// src/components/detail/TransactionsTab.tsx
import { useTransactions } from "../../hooks/useTransactions";

function fmtMoney(n: number) {
  const sign = n < 0 ? "-" : "";
  const abs = Math.abs(n);
  return `${sign}$${abs.toFixed(2)}`;
}

export function TransactionsTab({ businessId }: { businessId: string }) {
  const { data, loading, err, refresh } = useTransactions(businessId, 50);

  if (loading && !data) return <div style={{ padding: 12 }}>Loading transactions…</div>;
  if (err) return (
    <div style={{ padding: 12 }}>
      <div style={{ marginBottom: 8 }}>Error: {err}</div>
      <button onClick={refresh}>Retry</button>
    </div>
  );

  const txns = data?.transactions ?? [];

  return (
    <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <div style={{ fontWeight: 600 }}>Recent Transactions</div>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <small>
            As of {data?.as_of ? new Date(data.as_of).toLocaleString() : "—"}
          </small>
          <button onClick={refresh}>Refresh</button>
        </div>
      </div>

      <div style={{ border: "1px solid #e5e5e5", borderRadius: 8, overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ textAlign: "left", background: "#fafafa" }}>
              <th style={{ padding: "10px 12px" }}>When</th>
              <th style={{ padding: "10px 12px" }}>Description</th>
              <th style={{ padding: "10px 12px" }}>Account</th>
              <th style={{ padding: "10px 12px" }}>Category</th>
              <th style={{ padding: "10px 12px", textAlign: "right" }}>Amount</th>
            </tr>
          </thead>
          <tbody>
            {txns.map((t) => (
              <tr key={t.id} style={{ borderTop: "1px solid #eee" }}>
                <td style={{ padding: "10px 12px", whiteSpace: "nowrap" }}>
                  {new Date(t.occurred_at).toLocaleString()}
                </td>
                <td style={{ padding: "10px 12px" }}>
                  <div style={{ fontWeight: 500 }}>{t.description}</div>
                  <small style={{ opacity: 0.75 }}>
                    event {t.source_event_id.slice(-6)}
                    {t.counterparty_hint ? ` · hint: ${t.counterparty_hint}` : ""}
                  </small>
                </td>
                <td style={{ padding: "10px 12px" }}>{t.account}</td>
                <td style={{ padding: "10px 12px" }}>{t.category}</td>
                <td style={{ padding: "10px 12px", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                  {fmtMoney(t.amount)}
                </td>
              </tr>
            ))}
            {txns.length === 0 && (
              <tr>
                <td colSpan={5} style={{ padding: 12, opacity: 0.75 }}>
                  No transactions found for this business yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {data?.last_event_occurred_at && (
        <small style={{ opacity: 0.75 }}>
          Latest event occurred at {new Date(data.last_event_occurred_at).toLocaleString()}.
        </small>
      )}
    </div>
  );
}
