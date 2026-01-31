// frontend/src/app/routes/BusinessSelectPage.tsx
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchDashboard } from "../../api/demo";
import { assertBusinessId } from "../../utils/businessId";
import { useAppState } from "../state/appState";

type Card = {
  business_id: string;
  name?: string | null;
  subtitle?: string | null;
};

export default function BusinessSelectPage() {
  const navigate = useNavigate();
  const { setActiveBusinessId } = useAppState();
  const [cards, setCards] = useState<Card[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setErr(null);

    fetchDashboard(controller.signal)
      .then((res) => {
        const list = (res?.cards ?? []) as Card[];
        setCards(list);
      })
      .catch((e: any) => {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setErr(e?.message ?? "Failed to load businesses");
      })
      .finally(() => setLoading(false));

    return () => controller.abort();
  }, []);

  const handleSelect = (rawId: string) => {
    const id = assertBusinessId(rawId, "BusinessSelectPage");
    if (!id) return;
    setActiveBusinessId(id);
    navigate(`/app/${id}/dashboard`);
  };

  return (
    <div style={{ padding: 24, maxWidth: 900, margin: "0 auto" }}>
      <h2 style={{ margin: 0 }}>Select a business</h2>
      <p style={{ opacity: 0.8, marginTop: 8 }}>
        Choose a workspace to view Health, Dashboard, Ledger, Trends, and Simulator.
      </p>

      {loading && <div>Loading…</div>}
      {err && <div style={{ color: "crimson" }}>Error: {err}</div>}

      {!loading && !err && cards.length === 0 && (
        <div style={{ opacity: 0.85 }}>
          No demo businesses found. Run your demo bootstrap / simulator generate, then refresh.
        </div>
      )}

      <div style={{ display: "grid", gap: 12, marginTop: 16 }}>
        {cards.map((c) => (
          <button
            key={c.business_id}
            type="button"
            onClick={() => handleSelect(c.business_id)}
            style={{
              textAlign: "left",
              padding: 14,
              borderRadius: 12,
              border: "1px solid rgba(255,255,255,0.12)",
              background: "rgba(255,255,255,0.04)",
              cursor: "pointer",
            }}
          >
            <div style={{ fontWeight: 700 }}>
              {c.name ?? "Demo business"}{" "}
              <span style={{ opacity: 0.6, fontWeight: 400 }}>({c.business_id})</span>
            </div>
            {c.subtitle ? <div style={{ opacity: 0.75, marginTop: 6 }}>{c.subtitle}</div> : null}
          </button>
        ))}
      </div>
    </div>
  );
}
