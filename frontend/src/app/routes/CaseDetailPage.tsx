import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { assignCase, getCase, getCaseTimeline, recomputeCase, scheduleCaseReview, type CaseDetailResponse } from "../../api/cases";

export default function CaseDetailPage() {
  const { businessId = "", caseId = "" } = useParams();
  const [detail, setDetail] = useState<CaseDetailResponse | null>(null);
  const [timeline, setTimeline] = useState<Array<{ id: string; event_type: string; payload_json: Record<string, unknown>; created_at: string }>>([]);
  const [recomputeResult, setRecomputeResult] = useState<Record<string, unknown> | null>(null);

  const load = () => {
    if (!caseId) return;
    void Promise.all([getCase(businessId, caseId), getCaseTimeline(businessId, caseId)]).then(([caseDetail, events]) => {
      setDetail(caseDetail);
      setTimeline(events);
    });
  };

  useEffect(() => {
    load();
  }, [caseId]);

  if (!detail) return <div>Loading case…</div>;

  return (
    <div>
      <h2>Case Detail</h2>
      <section>
        <h3>Governance</h3>
        <div>Assigned to: <input aria-label="Assigned to" defaultValue={detail.case.assigned_to ?? ""} onBlur={(e) => { void assignCase(businessId, caseId, e.target.value || null).then(load); }} /></div>
        <div>Next review: <input aria-label="Next review" type="datetime-local" defaultValue={detail.case.next_review_at ? detail.case.next_review_at.slice(0, 16) : ""} onBlur={(e) => { void scheduleCaseReview(businessId, caseId, e.target.value ? new Date(e.target.value).toISOString() : null).then(load); }} /></div>
        <div>SLA: {detail.case.sla_due_at ? new Date(detail.case.sla_due_at).toLocaleDateString() : "—"} {detail.case.sla_breached ? "(breached)" : ""}</div>
        {import.meta.env.DEV && (
          <div>
            <button type="button" onClick={() => void recomputeCase(businessId, caseId, false).then((res) => setRecomputeResult(res as Record<string, unknown>))}>Recompute</button>
            {recomputeResult && <pre>{JSON.stringify(recomputeResult, null, 2)}</pre>}
            {(recomputeResult as { diff?: { is_match?: boolean } } | null)?.diff?.is_match === false && (
              <button type="button" onClick={() => void recomputeCase(businessId, caseId, true).then((res) => { setRecomputeResult(res as Record<string, unknown>); load(); })}>Apply recompute</button>
            )}
          </div>
        )}
      </section>

      <section>
        <div>Severity: {detail.case.severity}</div>
        <div>Status: {detail.case.status}</div>
        <div>Domain: {detail.case.domain}</div>
      </section>

      <section>
        <h3>Evidence</h3>
        <ul>
          {detail.signals.map((signal) => (
            <li key={signal.signal_id}>
              {signal.title ?? signal.signal_id} · {signal.status} · <Link to={`/app/${businessId}/signals/${signal.signal_id}/explain`}>Explain</Link>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h3>Remediation</h3>
        <ul>{detail.plans.map((plan) => <li key={plan.id}>{plan.title} ({plan.status})</li>)}</ul>
        <ul>{detail.actions.map((action) => <li key={action.id}>{action.title} ({action.status})</li>)}</ul>
      </section>

      <section>
        <h3>Timeline</h3>
        <ul>{timeline.map((event) => <li key={event.id}>{event.created_at}: {event.event_type}</li>)}</ul>
      </section>
    </div>
  );
}
