import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchFirmOverview, type FirmOverviewBusiness, type RiskBand } from "../api/firm";
import PageHeader from "../components/common/PageHeader";
import DataStatusStrip from "../components/status/DataStatusStrip";
import styles from "./FirmDashboardPage.module.css";

function latestActivity(item: FirmOverviewBusiness): string {
  const latest = [item.latest_signal_at, item.latest_action_at]
    .filter((value): value is string => Boolean(value))
    .sort()
    .at(-1);
  if (!latest) return "—";
  const parsed = new Date(latest);
  if (Number.isNaN(parsed.getTime())) return "—";
  return parsed.toLocaleString();
}

export default function FirmDashboardPage() {
  const [rows, setRows] = useState<FirmOverviewBusiness[]>([]);
  const [generatedAt, setGeneratedAt] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const run = async () => {
      try {
        setError(null);
        const payload = await fetchFirmOverview();
        const sorted = [...payload.businesses].sort(
          (a, b) => b.risk_score - a.risk_score || a.business_name.localeCompare(b.business_name)
        );
        setRows(sorted);
        setGeneratedAt(payload.generated_at);
      } catch (e: any) {
        setError(e?.message ?? "Failed to load firm dashboard.");
      }
    };
    void run();
  }, []);

  const topThree = useMemo(() => rows.slice(0, 3), [rows]);
  const statusBusinessId = rows[0]?.business_id ?? "";

  return (
    <div className={styles.page}>
      <PageHeader
        title="Firm Risk Dashboard"
        subtitle={generatedAt ? `Generated ${new Date(generatedAt).toLocaleString()}` : "Overview of firm-level risk"}
      />

      {statusBusinessId ? <DataStatusStrip businessId={statusBusinessId} /> : null}
      {error ? <div role="alert">{error}</div> : null}

      <section className={styles.cards} aria-label="Top risk businesses">
        {topThree.map((business) => (
          <article className={styles.card} key={business.business_id}>
            <div className={styles.cardTitle}>{business.business_name}</div>
            <div className={styles.cardScore}>{business.risk_score}</div>
            <span className={`${styles.riskBand} ${styles[business.risk_band]}`}>{business.risk_band}</span>
          </article>
        ))}
      </section>

      <table className={styles.table}>
        <thead>
          <tr>
            <th>Business</th>
            <th>Risk Score</th>
            <th>Risk Band</th>
            <th>Open Signals</th>
            <th>Open Actions</th>
            <th>Latest Activity</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((business) => (
            <tr key={business.business_id}>
              <td>{business.business_name}</td>
              <td>{business.risk_score}</td>
              <td>
                <span
                  data-testid={`risk-band-${business.business_id}`}
                  data-band={business.risk_band}
                  className={`${styles.riskBand} ${styles[business.risk_band as RiskBand]}`}
                >
                  {business.risk_band}
                </span>
              </td>
              <td>{business.open_signals}</td>
              <td>{business.open_actions}</td>
              <td>{latestActivity(business)}</td>
              <td>
                <div className={styles.ctas}>
                  <button onClick={() => navigate(`/app/${business.business_id}/advisor`)}>View Inbox</button>
                  <button onClick={() => navigate(`/app/${business.business_id}/signals`)}>View Signals</button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
