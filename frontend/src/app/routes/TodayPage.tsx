import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { completeWorkItem, listWorkItems, snoozeWorkItem, type WorkItem } from "../../api/work";
import { getLastTick, tickSystem, type LastTickResponse } from "../../api/system";

export default function TodayPage() {
  const { businessId = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const [rows, setRows] = useState<WorkItem[]>([]);
  const [lastTick, setLastTick] = useState<LastTickResponse>(null);
  const [refreshing, setRefreshing] = useState(false);

  const filters = useMemo(
    () => ({
      assignedOnly: searchParams.get("assigned_only") === "true",
      highCritical: searchParams.get("case_severity_gte") === "high",
      openOnly: (searchParams.get("status") as "open" | "snoozed" | "completed" | null) ?? "open",
      priorityGte: Number(searchParams.get("priority_gte") ?? "0"),
      dueWindow: searchParams.get("due_window") ?? "",
      sort: (searchParams.get("sort") as "priority" | "due_at" | "created_at" | null) ?? "priority",
    }),
    [searchParams],
  );

  const load = useCallback(() => {
    if (!businessId) return Promise.resolve();
    const dueBefore = filters.dueWindow
      ? new Date(Date.now() + Number(filters.dueWindow) * 24 * 60 * 60 * 1000).toISOString()
      : undefined;
    return listWorkItems(businessId, {
      status: filters.openOnly,
      assigned_only: filters.assignedOnly,
      case_severity_gte: filters.highCritical ? "high" : undefined,
      priority_gte: filters.priorityGte > 0 ? filters.priorityGte : undefined,
      due_before: dueBefore,
      sort: filters.sort,
    }).then((res) => setRows(res.items));
  }, [businessId, filters]);

  const loadLastTick = useCallback(() => {
    if (!businessId) return Promise.resolve();
    return getLastTick(businessId).then((result) => setLastTick(result));
  }, [businessId]);

  useEffect(() => {
    void load();
    void loadLastTick();
  }, [load, loadLastTick]);

  const setToggle = (key: string, value: boolean) => {
    setSearchParams((params) => {
      if (value) params.set(key, "true");
      else params.delete(key);
      return params;
    });
  };

  const onComplete = async (workItemId: string) => {
    if (!businessId) return;
    await completeWorkItem(businessId, workItemId);
    await load();
  };

  const onRefreshQueue = async () => {
    if (!businessId) return;
    setRefreshing(true);
    try {
      await tickSystem({ business_id: businessId, apply_recompute: false, materialize_work: true });
      await load();
      await loadLastTick();
    } finally {
      setRefreshing(false);
    }
  };

  const onSnooze = async (workItemId: string) => {
    if (!businessId) return;
    const snoozedUntil = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();
    await snoozeWorkItem(businessId, workItemId, snoozedUntil);
    await load();
  };

  return (
    <div>
      <h2>Advisor Today</h2>
      <div>
        <button type="button" onClick={() => void onRefreshQueue()} disabled={refreshing}>
          {refreshing ? "Refreshing queue…" : "Refresh queue"}
        </button>
        {lastTick?.finished_at ? <span>Last refreshed: {new Date(lastTick.finished_at).toLocaleString()}</span> : null}
        <label><input type="checkbox" checked={filters.assignedOnly} onChange={(e) => setToggle("assigned_only", e.target.checked)} /> Assigned only</label>
        <label><input type="checkbox" checked={filters.highCritical} onChange={(e) => setSearchParams((params) => { if (e.target.checked) params.set("case_severity_gte", "high"); else params.delete("case_severity_gte"); return params; })} /> High/Critical</label>
        <select value={filters.openOnly} onChange={(e) => setSearchParams((params) => { params.set("status", e.target.value); return params; })}>
          <option value="open">Open</option><option value="snoozed">Snoozed</option><option value="completed">Completed</option>
        </select>
        <select value={filters.dueWindow} onChange={(e) => setSearchParams((params) => { if (e.target.value) params.set("due_window", e.target.value); else params.delete("due_window"); return params; })}>
          <option value="">Any due date</option><option value="1">Due in 1 day</option><option value="3">Due in 3 days</option><option value="7">Due in 7 days</option>
        </select>
        <select value={filters.sort} onChange={(e) => setSearchParams((params) => { params.set("sort", e.target.value); return params; })}>
          <option value="priority">Priority</option><option value="due_at">Due date</option><option value="created_at">Created</option>
        </select>
      </div>
      <table>
        <thead><tr><th>Work type</th><th>Case severity</th><th>Case domain</th><th>Due date</th><th>Priority</th><th>Assigned to</th><th>Quick actions</th></tr></thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>{row.type}</td>
              <td>{row.case_severity}</td>
              <td>{row.case_domain}</td>
              <td>{row.due_at ? new Date(row.due_at).toLocaleString() : "—"}</td>
              <td>{row.priority}</td>
              <td>{row.assigned_to ?? "—"}</td>
              <td>
                <button type="button" onClick={() => void onComplete(row.id)}>Mark complete</button>
                <button type="button" onClick={() => void onSnooze(row.id)}>Snooze</button>
                <Link to={`/app/${businessId}/cases/${row.case_id}`}>Go to Case</Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
