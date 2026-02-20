import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { listCases, type CaseSummary } from "../../api/cases";

export default function TodayPage() {
  const { businessId = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const [rows, setRows] = useState<CaseSummary[]>([]);

  const filters = useMemo(
    () => ({
      slaBreached: searchParams.get("sla_breached") === "true",
      highCritical: searchParams.get("severity_gte") === "high",
      noPlan: searchParams.get("no_plan") === "true",
      planOverdue: searchParams.get("plan_overdue") === "true",
      openedWindow: searchParams.get("opened_window") ?? "",
      sort: (searchParams.get("sort") as "sla" | "severity" | "activity" | null) ?? "sla",
    }),
    [searchParams],
  );

  useEffect(() => {
    if (!businessId) return;
    const openedSince = filters.openedWindow
      ? new Date(Date.now() - Number(filters.openedWindow) * 24 * 60 * 60 * 1000).toISOString()
      : undefined;
    void listCases(businessId, {
      sort: filters.sort,
      sla_breached: filters.slaBreached || undefined,
      severity_gte: filters.highCritical ? "high" : undefined,
      no_plan: filters.noPlan || undefined,
      plan_overdue: filters.planOverdue || undefined,
      opened_since: openedSince,
    }).then((res) => setRows(res.items));
  }, [businessId, filters]);

  const setToggle = (key: string, value: boolean) => {
    setSearchParams((params) => {
      if (value) params.set(key, "true");
      else params.delete(key);
      return params;
    });
  };

  return (
    <div>
      <h2>Advisor Today</h2>
      <div>
        <label><input type="checkbox" checked={filters.slaBreached} onChange={(e) => setToggle("sla_breached", e.target.checked)} /> SLA breached</label>
        <label><input type="checkbox" checked={filters.highCritical} onChange={(e) => setSearchParams((params) => { if (e.target.checked) params.set("severity_gte", "high"); else params.delete("severity_gte"); return params; })} /> High/Critical</label>
        <label><input type="checkbox" checked={filters.noPlan} onChange={(e) => setToggle("no_plan", e.target.checked)} /> No plan</label>
        <label><input type="checkbox" checked={filters.planOverdue} onChange={(e) => setToggle("plan_overdue", e.target.checked)} /> Plan overdue</label>
        <select value={filters.openedWindow} onChange={(e) => setSearchParams((params) => { if (e.target.value) params.set("opened_window", e.target.value); else params.delete("opened_window"); return params; })}>
          <option value="">Any age</option><option value="7">New (7d)</option><option value="14">New (14d)</option>
        </select>
        <select value={filters.sort} onChange={(e) => setSearchParams((params) => { params.set("sort", e.target.value); return params; })}>
          <option value="sla">SLA urgency</option><option value="severity">Severity</option><option value="activity">Last activity</option>
        </select>
      </div>
      <table>
        <thead><tr><th>Severity</th><th>Status</th><th>Domain</th><th>Age</th><th>SLA</th><th>Plan</th><th>Last activity</th><th>Assigned to</th></tr></thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>{row.severity}</td>
              <td><Link to={`/app/${businessId}/cases/${row.id}`}>{row.status}</Link></td>
              <td>{row.domain}</td>
              <td>{row.age_days ?? "—"}</td>
              <td>{row.sla_due_at ? new Date(row.sla_due_at).toLocaleDateString() : "—"} {row.sla_breached ? "(breached)" : ""}</td>
              <td>{row.plan_state ?? "none"}</td>
              <td>{new Date(row.last_activity_at).toLocaleString()}</td>
              <td>{row.assigned_to ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
