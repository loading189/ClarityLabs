import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchActionTriage, type ActionTriageItem } from "../api/actions";
import { useBusinessesMine } from "../hooks/useBusinessesMine";
import ActionDetailDrawer from "../features/actions/ActionDetailDrawer";
import styles from "./AdvisorInboxPage.module.css";

type AssignedFilter = "me" | "unassigned" | "any";
type StatusFilter = "open" | "snoozed" | "done" | "ignored";

function formatDate(value: string) {
  return value.split("T")[0];
}

function formatPriority(priority: number) {
  if (priority >= 5) return "Critical";
  if (priority >= 4) return "High";
  if (priority >= 3) return "Medium";
  return "Low";
}

export default function AdvisorInboxPage() {
  const { businesses } = useBusinessesMine();
  const [status, setStatus] = useState<StatusFilter>("open");
  const [assigned, setAssigned] = useState<AssignedFilter>("any");
  const [businessId, setBusinessId] = useState<string>("all");
  const [actions, setActions] = useState<ActionTriageItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<ActionTriageItem | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetchActionTriage(businessId, { status, assigned });
      setActions(response.actions ?? []);
    } catch (err: any) {
      setError(err?.message ?? "Failed to load advisor inbox");
    } finally {
      setLoading(false);
    }
  }, [assigned, businessId, status]);

  useEffect(() => {
    void load();
  }, [load]);

  const businessOptions = useMemo(() => {
    return [
      { business_id: "all", business_name: "All businesses" },
      ...businesses,
    ];
  }, [businesses]);

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <h2>Advisor Inbox</h2>
          <p className={styles.muted}>Triage actions across all assigned clients.</p>
        </div>
        <div className={styles.filters}>
          <select
            className={styles.select}
            value={status}
            onChange={(event) => setStatus(event.target.value as StatusFilter)}
          >
            <option value="open">Open</option>
            <option value="snoozed">Snoozed</option>
            <option value="done">Done</option>
            <option value="ignored">Ignored</option>
          </select>
          <select
            className={styles.select}
            value={assigned}
            onChange={(event) => setAssigned(event.target.value as AssignedFilter)}
          >
            <option value="any">Any assignment</option>
            <option value="me">Assigned to me</option>
            <option value="unassigned">Unassigned</option>
          </select>
          <select
            className={styles.select}
            value={businessId}
            onChange={(event) => setBusinessId(event.target.value)}
          >
            {businessOptions.map((biz) => (
              <option key={biz.business_id} value={biz.business_id}>
                {biz.business_name}
              </option>
            ))}
          </select>
          <button type="button" className={styles.select} onClick={() => void load()}>
            Refresh
          </button>
        </div>
      </div>

      {loading && <div className={styles.muted}>Loading actions…</div>}
      {error && <div className={styles.error}>{error}</div>}
      {!loading && !error && actions.length === 0 && <div className={styles.muted}>No actions match filters.</div>}

      {!loading && actions.length > 0 && (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Business</th>
              <th>Priority</th>
              <th>Title</th>
              <th>Summary</th>
              <th>Created</th>
              <th>Assigned</th>
            </tr>
          </thead>
          <tbody>
            {actions.map((action) => (
              <tr key={action.id} className={styles.row} onClick={() => setSelected(action)}>
                <td>{action.business_name}</td>
                <td>
                  <span className={styles.badge}>{formatPriority(action.priority)}</span>
                </td>
                <td>{action.title}</td>
                <td>{action.summary}</td>
                <td>{formatDate(action.created_at)}</td>
                <td>
                  {action.assigned_to_user?.name ??
                    action.assigned_to_user?.email ??
                    (action.assigned_to_user_id ? "Assigned" : "Unassigned")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <ActionDetailDrawer
        open={Boolean(selected)}
        action={selected}
        onClose={() => setSelected(null)}
        onUpdated={load}
      />
    </div>
  );
}
