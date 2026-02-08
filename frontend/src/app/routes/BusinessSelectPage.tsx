import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { createBusiness, deleteBusiness, joinBusiness } from "../../api/businesses";
import { fetchConfig, type AppConfig } from "../../api/config";
import { assertBusinessId } from "../../utils/businessId";
import { useBusinessesMine } from "../../hooks/useBusinessesMine";
import { useAppState } from "../state/appState";

type JoinState = {
  businessId: string;
  role: string;
};

export default function BusinessSelectPage() {
  const navigate = useNavigate();
  const { setActiveBusinessId } = useAppState();
  const { businesses, loading, error, reload } = useBusinessesMine();
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [createLoading, setCreateLoading] = useState(false);
  const [createErr, setCreateErr] = useState<string | null>(null);
  const [joinState, setJoinState] = useState<JoinState>({ businessId: "", role: "advisor" });
  const [joinLoading, setJoinLoading] = useState(false);
  const [joinErr, setJoinErr] = useState<string | null>(null);
  const [deleteErr, setDeleteErr] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    fetchConfig()
      .then((next) => {
        if (mounted) setConfig(next);
      })
      .catch((err: any) => {
        if (mounted) setConfigError(err?.message ?? "Failed to load config");
      });
    return () => {
      mounted = false;
    };
  }, []);

  const handleSelect = (rawId: string) => {
    const id = assertBusinessId(rawId, "BusinessSelectPage");
    if (!id) return;
    setActiveBusinessId(id);
    navigate(`/app/${id}/assistant`);
  };

  const handleCreate = async () => {
    if (!newName.trim()) {
      setCreateErr("Business name is required");
      return;
    }
    setCreateErr(null);
    setCreateLoading(true);
    try {
      const created = await createBusiness({ name: newName.trim() });
      setActiveBusinessId(created.business.id);
      await reload();
      navigate(`/app/${created.business.id}/assistant`);
    } catch (err: any) {
      setCreateErr(err?.message ?? "Failed to create business");
    } finally {
      setCreateLoading(false);
    }
  };

  const handleJoin = async () => {
    if (!joinState.businessId.trim()) {
      setJoinErr("Business ID is required");
      return;
    }
    setJoinErr(null);
    setJoinLoading(true);
    try {
      await joinBusiness(joinState.businessId.trim(), { role: joinState.role });
      await reload();
    } catch (err: any) {
      setJoinErr(err?.message ?? "Failed to join business");
    } finally {
      setJoinLoading(false);
    }
  };

  const handleDelete = async (businessId: string, businessName?: string | null) => {
    setDeleteErr(null);
    const promptValue = window.prompt(
      `Type DELETE or ${businessName ?? businessId} to confirm deletion.`
    );
    if (!promptValue) return;
    const normalized = promptValue.trim().toLowerCase();
    const expectedName = (businessName ?? "").trim().toLowerCase();
    if (normalized !== "delete" && normalized !== expectedName) return;

    try {
      await deleteBusiness(businessId);
      await reload();
    } catch (err: any) {
      setDeleteErr(err?.message ?? "Failed to delete business");
    }
  };

  const pilotModeEnabled = config?.pilot_mode_enabled ?? false;
  const allowBusinessDelete = config?.allow_business_delete ?? false;

  return (
    <div style={{ padding: 24, maxWidth: 900, margin: "0 auto" }}>
      <h2 style={{ margin: 0 }}>Manage businesses</h2>
      <p style={{ opacity: 0.8, marginTop: 8 }}>
        Create a new business or switch to an existing workspace.
      </p>

      {configError && (
        <div style={{ color: "crimson", marginTop: 12 }}>Config error: {configError}</div>
      )}

      <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
        <input
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          placeholder="Business name"
        />
        <button onClick={handleCreate} disabled={createLoading}>
          {createLoading ? "Creating…" : "Create business"}
        </button>
      </div>
      {createErr && <div style={{ color: "crimson", marginTop: 8 }}>Error: {createErr}</div>}

      {pilotModeEnabled && (
        <div style={{ marginTop: 16, padding: 12, border: "1px solid rgba(255,255,255,0.12)", borderRadius: 12 }}>
          <div style={{ fontWeight: 600 }}>Dev: Join business</div>
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <input
              value={joinState.businessId}
              onChange={(e) => setJoinState((prev) => ({ ...prev, businessId: e.target.value }))}
              placeholder="Business ID"
            />
            <select
              value={joinState.role}
              onChange={(e) => setJoinState((prev) => ({ ...prev, role: e.target.value }))}
            >
              <option value="advisor">advisor</option>
              <option value="staff">staff</option>
              <option value="viewer">viewer</option>
              <option value="owner">owner</option>
            </select>
            <button onClick={handleJoin} disabled={joinLoading}>
              {joinLoading ? "Joining…" : "Join"}
            </button>
          </div>
          {joinErr && <div style={{ color: "crimson", marginTop: 8 }}>Error: {joinErr}</div>}
        </div>
      )}

      {loading && <div style={{ marginTop: 16 }}>Loading…</div>}
      {error && <div style={{ color: "crimson", marginTop: 16 }}>Error: {error}</div>}

      {!loading && !error && businesses.length === 0 && (
        <div style={{ opacity: 0.85, marginTop: 16 }}>
          No businesses yet — create your first workspace.
        </div>
      )}

      {deleteErr && <div style={{ color: "crimson", marginTop: 12 }}>Error: {deleteErr}</div>}

      <div style={{ display: "grid", gap: 12, marginTop: 16 }}>
        {businesses.map((biz) => (
          <div key={biz.business_id} style={{ border: "1px solid rgba(255,255,255,0.12)", borderRadius: 12, padding: 14 }}>
            <button
              type="button"
              onClick={() => handleSelect(biz.business_id)}
              style={{ textAlign: "left", width: "100%" }}
            >
              <div style={{ fontWeight: 700 }}>
                {biz.business_name} <span style={{ opacity: 0.6, fontWeight: 400 }}>({biz.business_id})</span>
              </div>
              <div style={{ opacity: 0.75, marginTop: 6 }}>Role: {biz.role}</div>
            </button>
            {allowBusinessDelete && biz.role === "owner" && (
              <button style={{ marginTop: 8 }} onClick={() => handleDelete(biz.business_id, biz.business_name)}>
                Delete business
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
