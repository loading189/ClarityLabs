import { useEffect, useMemo, useState } from "react";
import type { BusinessDetail, Signal } from "../../types";
import SignalGrid from "./SignalGrid";
import SignalDetail from "./SignalDetail";

function sevRank(sev?: string) {
  if (sev === "red") return 3;
  if (sev === "yellow") return 2;
  return 1;
}

export default function SignalsTab({ detail }: { detail: BusinessDetail }) {
  const signals = (detail.signals ?? []) as Signal[];

  // Sort once for stable UI behavior
  const sorted = useMemo(() => {
    return [...signals].sort((a, b) => {
      const r = sevRank(b.severity) - sevRank(a.severity);
      if (r !== 0) return r;

      const p = (b.priority ?? 0) - (a.priority ?? 0);
      if (p !== 0) return p;

      return String(a.key).localeCompare(String(b.key));
    });
  }, [signals]);

  // Keep selection stable across renders AND reset when business changes
  const [selectedKey, setSelectedKey] = useState<string | null>(sorted[0]?.key ?? null);

  // When switching businesses, default to the top signal for that business
  useEffect(() => {
    setSelectedKey(sorted[0]?.key ?? null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail.business_id]); // only when business changes

  // If keys change (signals recomputed), keep selection valid
  const selected = useMemo(() => {
    if (!sorted.length) return null;
    return sorted.find((s) => s.key === selectedKey) ?? sorted[0] ?? null;
  }, [sorted, selectedKey]);

  if (!sorted.length) {
    return (
      <div style={{ paddingTop: 8 }}>
        <h3 style={{ marginTop: 0 }}>Signals</h3>
        <div style={{ opacity: 0.7 }}>No signals yet.</div>
      </div>
    );
  }

  return (
    <div style={{ paddingTop: 8 }}>
      <h3 style={{ marginTop: 0 }}>Signals</h3>

      <div className="signalDashboardLayout">
        <SignalGrid
          signals={sorted}
          selectedKey={selectedKey}
          onSelect={(s) => setSelectedKey(s.key)}
        />

        {/* Pass businessId so SignalDetail can fetch related transactions via evidence_refs */}
        {selected && (
          <SignalDetail
            businessId={detail.business_id}
            signal={selected}
          />
        )}
      </div>

      {/* Optional: keep your ledger preview below */}
      {detail.ledger_preview && detail.ledger_preview.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <div style={{ fontSize: 12, opacity: 0.8, marginBottom: 6 }}>Ledger preview</div>
          <div style={{ border: "1px solid #e5e7eb", borderRadius: 12, overflow: "hidden" }}>
            {detail.ledger_preview.slice(0, 8).map((row: any, i: number) => (
              <div
                key={i}
                style={{
                  display: "grid",
                  gridTemplateColumns: "140px 1fr 120px",
                  gap: 10,
                  padding: 10,
                  borderBottom: "1px solid #f3f4f6",
                  fontSize: 12,
                }}
              >
                <div>{String(row.date ?? "")}</div>
                <div style={{ opacity: 0.85 }}>{String(row.description ?? "")}</div>
                <div style={{ textAlign: "right" }}>
                  {row.balance != null ? `$${Number(row.balance).toFixed(2)}` : ""}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
