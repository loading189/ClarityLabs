import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchDashboard, seedDemo } from "../../api/demo";
import { createBusiness, deleteBusiness } from "../../api/businesses";
import { seedSimV2 } from "../../api/simV2";
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
  const [newName, setNewName] = useState("New Demo Business");
  const [isDemo, setIsDemo] = useState(true);
  const [demoLoading, setDemoLoading] = useState(false);
  const [demoErr, setDemoErr] = useState<string | null>(null);
  const isDev = import.meta.env.DEV;

  const load = () => {
    const controller = new AbortController();
    setLoading(true);
    setErr(null);

    fetchDashboard(controller.signal)
      .then((res) => setCards((res?.cards ?? []) as Card[]))
      .catch((e: any) => {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setErr(e?.message ?? "Failed to load businesses");
      })
      .finally(() => setLoading(false));

    return () => controller.abort();
  };

  useEffect(() => load(), []);

  const handleSelect = (rawId: string) => {
    const id = assertBusinessId(rawId, "BusinessSelectPage");
    if (!id) return;
    setActiveBusinessId(id);
    navigate(`/app/${id}/assistant`);
  };

  const handleCreate = async () => {
    const created = await createBusiness({ name: newName, is_demo: isDemo });
    setActiveBusinessId(created.id);
    if (isDemo) {
      await seedSimV2({ business_id: created.id, preset_id: "healthy", mode: "replace" });
    }
    navigate(`/app/${created.id}/assistant`);
  };

  const handleStartDemo = async () => {
    setDemoLoading(true);
    setDemoErr(null);
    try {
      const seeded = await seedDemo();
      const id = assertBusinessId(seeded.business_id, "BusinessSelectPage demo seed");
      if (!id) return;
      setActiveBusinessId(id);
      navigate(`/app/${id}/assistant`);
    } catch (e: any) {
      setDemoErr(e?.message ?? "Failed to start demo");
    } finally {
      setDemoLoading(false);
    }
  };

  const handleDelete = async (businessId: string, businessName?: string | null) => {
    const confirmation = window.prompt(`Type DELETE to remove ${businessName ?? businessId}`);
    if (confirmation !== "DELETE") return;
    await deleteBusiness(businessId);
    navigate("/app/select");
    load();
  };

  return (
    <div style={{ padding: 24, maxWidth: 900, margin: "0 auto" }}>
      <h2 style={{ margin: 0 }}>Select a business</h2>
      <p style={{ opacity: 0.8, marginTop: 8 }}>Choose a workspace, onboard a business, or delete one.</p>

      {isDev && (
        <div style={{ marginTop: 12, padding: 12, border: "1px solid rgba(255,255,255,0.12)", borderRadius: 12 }}>
          <div style={{ fontWeight: 600 }}>Demo</div>
          <p style={{ opacity: 0.75, marginTop: 6 }}>
            Seed the deterministic golden-path demo data and jump into the Assistant.
          </p>
          <button onClick={handleStartDemo} disabled={demoLoading}>
            {demoLoading ? "Starting demo…" : "Start Demo"}
          </button>
          {demoErr && <div style={{ color: "crimson", marginTop: 8 }}>Error: {demoErr}</div>}
        </div>
      )}

      <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
        <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Business name" />
        <label>
          <input type="checkbox" checked={isDemo} onChange={(e) => setIsDemo(e.target.checked)} /> Demo
        </label>
        <button onClick={handleCreate}>Create business</button>
      </div>

      {loading && <div>Loading…</div>}
      {err && <div style={{ color: "crimson" }}>Error: {err}</div>}

      {!loading && !err && cards.length === 0 && <div style={{ opacity: 0.85 }}>No businesses yet — create one.</div>}

      <div style={{ display: "grid", gap: 12, marginTop: 16 }}>
        {cards.map((c) => (
          <div key={c.business_id} style={{ border: "1px solid rgba(255,255,255,0.12)", borderRadius: 12, padding: 14 }}>
            <button type="button" onClick={() => handleSelect(c.business_id)} style={{ textAlign: "left", width: "100%" }}>
              <div style={{ fontWeight: 700 }}>
                {c.name ?? "Demo business"} <span style={{ opacity: 0.6, fontWeight: 400 }}>({c.business_id})</span>
              </div>
              {c.subtitle ? <div style={{ opacity: 0.75, marginTop: 6 }}>{c.subtitle}</div> : null}
            </button>
            <button style={{ marginTop: 8 }} onClick={() => handleDelete(c.business_id, c.name)}>
              Delete business
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
