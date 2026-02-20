import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { createActionFromSignal } from "../../api/actions";
import { fetchSignalExplain, type SignalExplainCaseFile } from "../../api/signalExplain";
import { ledgerPath } from "../../app/routes/routeUtils";
import styles from "./SignalExplainPage.module.css";

export default function SignalExplainPage() {
  const { businessId = "", signalId = "" } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState<SignalExplainCaseFile | null>(null);

  useEffect(() => {
    if (!businessId || !signalId) return;
    void fetchSignalExplain(businessId, signalId).then(setData);
  }, [businessId, signalId]);

  const handlePrimary = async () => {
    if (!businessId || !signalId || !data) return;
    const actionId = data.linked_action_id ?? (await createActionFromSignal(businessId, signalId)).action_id;
    navigate(`/app/${businessId}/inbox?action_id=${encodeURIComponent(actionId)}`);
  };

  if (!data) return <div>Loading explain…</div>;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h2>{data.title}</h2>
        <div>
          <span className={styles.chip}>{data.severity ?? "—"}</span>
          <span className={styles.chip}>{data.status}</span>
        </div>
      </header>

      <section>
        <h3>{data.narrative.headline}</h3>
        <h4>Why it matters</h4>
        <ul>{data.narrative.why_it_matters.map((item) => <li key={item}>{item}</li>)}</ul>
        <h4>What changed</h4>
        <ul>{data.narrative.what_changed.map((item) => <li key={item}>{item}</li>)}</ul>
      </section>

      {data.case_id ? (
        <p>
          Parent case: <Link to={`/app/${businessId}/cases/${data.case_id}`}>{data.case_id}</Link>
        </p>
      ) : null}

      <section>
        <h3>Evidence</h3>
        <div className={styles.stats}>
          <div>Baseline: {data.case_evidence.stats.baseline_total ?? "—"}</div>
          <div>Current: {data.case_evidence.stats.current_total ?? "—"}</div>
          <div>% Change: {data.case_evidence.stats.pct_change ?? "—"}</div>
        </div>
        <table className={styles.table}>
          <thead><tr><th>Date</th><th>Name</th><th>Amount</th><th /></tr></thead>
          <tbody>
            {data.case_evidence.top_transactions.map((txn) => (
              <tr key={txn.source_event_id}>
                <td>{txn.occurred_at?.split("T")[0] ?? "—"}</td>
                <td>{txn.name ?? txn.vendor ?? txn.memo ?? "—"}</td>
                <td>{txn.amount ?? "—"}</td>
                <td>
                  <Link to={ledgerPath(businessId, { anchor_source_event_id: txn.source_event_id })}>View in Ledger</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <button type="button" onClick={() => void handlePrimary()}>
        {data.linked_action_id ? "Open in Inbox" : "Create Action"}
      </button>
    </div>
  );
}
