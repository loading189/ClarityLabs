// src/components/detail/SignalDetail.tsx
import { useMemo } from "react";
import type { Signal } from "../../types";
import { useTransactions } from "../../hooks/useTransactions";

type Props = {
  businessId: string;
  signal: Signal;
};

function extractSourceEventIds(signal: Signal): string[] {
  const refs = signal.evidence_refs ?? [];
  const ids = refs
    .map((r: any) => String(r?.source_event_id ?? "").trim())
    .filter(Boolean);
  return Array.from(new Set(ids));
}

export default function SignalDetail({ businessId, signal }: Props) {
  const sourceEventIds = useMemo(() => extractSourceEventIds(signal), [signal]);

  // Only fetch if we actually have refs
  const shouldFetch = sourceEventIds.length > 0;
  const { data, loading, err, refresh } = useTransactions(
    shouldFetch ? businessId : null,
    50,
    shouldFetch ? sourceEventIds : undefined
  );

  return (
    <div className="signalDetail">
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
        <div>
          <div style={{ fontWeight: 700 }}>{signal.title}</div>
          <div style={{ fontSize: 12, opacity: 0.75 }}>
            {signal.dimension} · {String(signal.severity).toUpperCase()} · priority {signal.priority}
          </div>
        </div>

        {shouldFetch && (
          <button onClick={refresh} disabled={loading}>
            {loading ? "Loading…" : "Refresh"}
          </button>
        )}
      </div>

      <div style={{ marginTop: 10 }}>{signal.message}</div>

      {signal.why && (
        <div style={{ marginTop: 10 }}>
          <strong>Why:</strong> {signal.why}
        </div>
      )}

      {signal.how_to_fix && (
        <div style={{ marginTop: 10 }}>
          <strong>Next:</strong> {signal.how_to_fix}
        </div>
      )}

      {signal.evidence && (
        <details style={{ marginTop: 10 }}>
          <summary>Evidence</summary>
          <pre style={{ marginTop: 8 }}>{JSON.stringify(signal.evidence, null, 2)}</pre>
        </details>
      )}

      {/* Drilldown transactions */}
      <div style={{ marginTop: 14 }}>
        <div style={{ fontSize: 12, opacity: 0.8, marginBottom: 6 }}>
          Related transactions {shouldFetch ? `(${sourceEventIds.length} refs)` : "(no refs)"}
        </div>

        {!shouldFetch && (
          <div style={{ opacity: 0.7 }}>
            This signal doesn’t yet include transaction references (evidence_refs).
          </div>
        )}

        {shouldFetch && err && (
          <div style={{ padding: 10, border: "1px solid #eee", borderRadius: 8 }}>
            Error loading transactions: {err}
          </div>
        )}

        {shouldFetch && loading && !data && <div style={{ opacity: 0.7 }}>Loading…</div>}

        {shouldFetch && data && (
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
                {(data.transactions ?? []).map((t) => (
                  <tr key={t.id} style={{ borderTop: "1px solid #eee" }}>
                    <td style={{ padding: "10px 12px", whiteSpace: "nowrap" }}>
                      {new Date(t.occurred_at).toLocaleString()}
                    </td>
                    <td style={{ padding: "10px 12px" }}>
                      <div style={{ fontWeight: 500 }}>{t.description}</div>
                      <small style={{ opacity: 0.75 }}>event {String(t.source_event_id).slice(-6)}</small>
                    </td>
                    <td style={{ padding: "10px 12px" }}>{t.account}</td>
                    <td style={{ padding: "10px 12px" }}>{t.category}</td>
                    <td style={{ padding: "10px 12px", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                      {t.amount < 0 ? "-" : ""}${Math.abs(t.amount).toFixed(2)}
                    </td>
                  </tr>
                ))}
                {(data.transactions ?? []).length === 0 && (
                  <tr>
                    <td colSpan={5} style={{ padding: 12, opacity: 0.75 }}>
                      No matching transactions returned for these refs.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
