import { useMemo, useState } from "react";
import { deleteBusiness } from "../../api/admin";
import styles from "./DeleteBusinessPanel.module.css";

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
    <div className={styles.panel}>
      <div className={styles.header}>
        <h3 className={styles.title}>Danger zone</h3>
        <button
          className={styles.button}
          onClick={() => {
            setErr(null);
            setConfirmOpen((v) => !v);
          }}
          disabled={loading}
          type="button"
        >
          Delete business
        </button>
      </div>

      <div className={styles.description}>
        This permanently deletes the business and all associated data.
      </div>

      {confirmOpen && (
        <div className={styles.confirmPanel}>
          <div className={styles.confirmText}>
            Type <strong>{requiredPhrase}</strong> to confirm.
          </div>

          <input
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            placeholder={requiredPhrase}
            className={styles.input}
            disabled={loading}
          />

          {err && <div className={styles.error}>{err}</div>}

          <div className={styles.actions}>
            <button
              className={styles.button}
              onClick={onConfirmDelete}
              disabled={!canDelete || loading}
              type="button"
            >
              {loading ? "Deleting…" : "Confirm delete"}
            </button>

            <button
              className={styles.button}
              onClick={() => {
                setConfirmOpen(false);
                setTyped("");
                setErr(null);
              }}
              disabled={loading}
              type="button"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
