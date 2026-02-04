import { useCallback, useEffect, useMemo, useState } from "react";
import { getAuditLog, type AuditLogOut } from "../../api/audit";
import styles from "./RecentChangesPanel.module.css";

const EVENT_LABELS: Record<string, string> = {
  categorization_change: "Categorization updated",
  rule_create: "Rule created",
  rule_update: "Rule updated",
  rule_delete: "Rule deleted",
  vendor_default_set: "Vendor default set",
  vendor_default_remove: "Vendor default removed",
};

function summarizeEvent(event: AuditLogOut): string {
  return EVENT_LABELS[event.event_type] ?? event.event_type.replace(/_/g, " ");
}

function detailLine(event: AuditLogOut): string | null {
  const after = event.after_state ?? {};
  if (after.category_name) {
    return `Category: ${after.category_name}`;
  }
  if (after.system_key) {
    return `System key: ${after.system_key}`;
  }
  if (event.rule_id) {
    return `Rule: ${event.rule_id}`;
  }
  return null;
}

export default function RecentChangesPanel({
  businessId,
  dataVersion,
  limit = 8,
}: {
  businessId: string;
  dataVersion: number;
  limit?: number;
}) {
  const [items, setItems] = useState<AuditLogOut[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!businessId) return;
    setLoading(true);
    setErr(null);
    try {
      const data = await getAuditLog(businessId, limit);
      setItems(data);
    } catch (e: any) {
      setErr(e?.message ?? "Failed to load audit log");
    } finally {
      setLoading(false);
    }
  }, [businessId, limit]);

  useEffect(() => {
    load();
  }, [load, dataVersion]);

  const list = useMemo(() => items.slice(0, limit), [items, limit]);

  return (
    <div className={styles.panel}>
      <div className={styles.headerRow}>
        <div>
          <h3 className={styles.title}>Recent changes</h3>
          <div className={styles.subtitle}>Append-only audit trail for categorization actions.</div>
        </div>
        <button className={styles.button} onClick={load} type="button">
          Refresh
        </button>
      </div>

      {err && <div className={styles.error}>Error: {err}</div>}
      {loading ? (
        <div className={styles.loading}>Loading audit log…</div>
      ) : list.length === 0 ? (
        <div className={styles.empty}>No recent changes yet.</div>
      ) : (
        <ul className={styles.list}>
          {list.map((event) => {
            const detail = detailLine(event);
            return (
              <li key={event.id} className={styles.item}>
                <div className={styles.itemHeader}>
                  <span className={styles.itemTitle}>{summarizeEvent(event)}</span>
                  <span className={styles.itemTime}>
                    {new Date(event.created_at).toLocaleString()}
                  </span>
                </div>
                <div className={styles.itemMeta}>
                  Actor: {event.actor}
                  {event.reason ? ` • ${event.reason}` : ""}
                </div>
                {detail && <div className={styles.itemDetail}>{detail}</div>}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
