import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { getCase, getCaseTimeline, type CaseDetailResponse } from "../../api/cases";

export default function CaseDetailPage() {
  const { businessId = "", caseId = "" } = useParams();
  const [detail, setDetail] = useState<CaseDetailResponse | null>(null);
  const [timeline, setTimeline] = useState<Array<{ id: string; event_type: string; payload_json: Record<string, unknown>; created_at: string }>>([]);

  useEffect(() => {
    if (!caseId) return;
    void Promise.all([getCase(businessId, caseId), getCaseTimeline(businessId, caseId)]).then(([caseDetail, events]) => {
      setDetail(caseDetail);
      setTimeline(events);
    });
  }, [caseId]);

  if (!detail) return <div>Loading case…</div>;

  return (
    <div>
      <h2>Case Detail</h2>
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
