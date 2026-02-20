import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams, useParams } from "react-router-dom";

import { listCases, type CaseSummary } from "../../api/cases";

export default function CaseCenterPage() {
  const { businessId = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const [rows, setRows] = useState<CaseSummary[]>([]);

  const filters = useMemo(
    () => ({
      status: searchParams.get("status") ?? "",
      severity: searchParams.get("severity") ?? "",
      domain: searchParams.get("domain") ?? "",
      q: searchParams.get("q") ?? "",
      sort: (searchParams.get("sort") as "aging" | "severity" | "activity" | null) ?? "activity",
    }),
    [searchParams],
  );

  useEffect(() => {
    if (!businessId) return;
    void listCases(businessId, { ...filters, status: filters.status || undefined, severity: filters.severity || undefined, domain: filters.domain || undefined, q: filters.q || undefined }).then((res) => setRows(res.items));
  }, [businessId, filters]);

  return (
    <div>
      <h2>Case Center</h2>
      <div>
        <input value={filters.q} placeholder="Search" onChange={(e) => setSearchParams((p) => { p.set("q", e.target.value); return p; })} />
        <select value={filters.status} onChange={(e) => setSearchParams((p) => { if (e.target.value) p.set("status", e.target.value); else p.delete("status"); return p; })}>
          <option value="">All status</option><option value="open">Open</option><option value="monitoring">Monitoring</option><option value="escalated">Escalated</option><option value="resolved">Resolved</option>
        </select>
        <select value={filters.sort} onChange={(e) => setSearchParams((p) => { p.set("sort", e.target.value); return p; })}>
          <option value="activity">Last activity</option><option value="aging">Aging</option><option value="severity">Severity</option>
        </select>
      </div>
      <table>
        <thead><tr><th>Severity</th><th>Status</th><th>Domain</th><th>Age</th><th>Last activity</th><th>Primary signal</th></tr></thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>{row.severity}</td>
              <td>{row.status}</td>
              <td>{row.domain}</td>
              <td>{new Date(row.opened_at).toLocaleDateString()}</td>
              <td>{new Date(row.last_activity_at).toLocaleString()}</td>
              <td><Link to={`/app/${businessId}/cases/${row.id}`}>{row.primary_signal_type ?? "—"}</Link></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
