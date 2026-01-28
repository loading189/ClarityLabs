import { useMemo, useState } from "react";
import { deleteBusiness } from "../../api/admin";

export function DeleteBusinessPanel({
  businessId,
  businessName,
  onDeleted,
}: {
  businessId: string;
  businessName?: string;
  onDeleted?: () => void;
}) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const requiredPhrase = useMemo(() => {
    // Make it unambiguous; avoids accidental deletion
    return `delete ${businessName || businessId}`;
  }, [businessName, businessId]);

  const canDelete = typed.trim().toLowerCase() === requiredPhrase.toLowerCase();

  async function onConfirmDelete() {
    setErr(null);
    setLoading(true);
    try {
      await deleteBusiness(businessId);
      setConfirmOpen(false);
      setTyped("");
      onDeleted?.();
    } catch (e: any) {
      setErr(e?.message ?? "Delete failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ border: "1px solid #fecaca", borderRadius: 12, padding: 12, marginTop: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <h3 style={{ margin: 0, color: "#991b1b" }}>Danger zone</h3>
        <button
          className="closeBtn"
          onClick={() => {
            setErr(null);
            setConfirmOpen((v) => !v);
          }}
          style={{
            border: "1px solid #ef4444",
            color: "#991b1b",
            opacity: loading ? 0.6 : 1,
          }}
          disabled={loading}
        >
          Delete business
        </button>
      </div>

      <div style={{ fontSize: 12, opacity: 0.85, marginTop: 8 }}>
        This permanently deletes the business and all associated data.
      </div>

      {confirmOpen && (
        <div style={{ marginTop: 12, borderTop: "1px solid #fee2e2", paddingTop: 12 }}>
          <div style={{ fontSize: 13, marginBottom: 8 }}>
            Type <strong>{requiredPhrase}</strong> to confirm.
          </div>

          <input
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            placeholder={requiredPhrase}
            style={{
              width: "100%",
              padding: 10,
              borderRadius: 10,
              border: "1px solid #e5e7eb",
              marginBottom: 10,
            }}
            disabled={loading}
          />

          {err && <div style={{ color: "#b91c1c", marginBottom: 10 }}>{err}</div>}

          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button
              className="closeBtn"
              onClick={onConfirmDelete}
              disabled={!canDelete || loading}
              style={{
                border: "1px solid #ef4444",
                opacity: !canDelete || loading ? 0.6 : 1,
              }}
            >
              {loading ? "Deleting…" : "Confirm delete"}
            </button>

            <button
              className="closeBtn"
              onClick={() => {
                setConfirmOpen(false);
                setTyped("");
                setErr(null);
              }}
              disabled={loading}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
