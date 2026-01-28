import ScoreRing from "./ScoreRing";
import RiskPill from "./RiskPill";
import type { DashboardCard } from "../types";
import styles from "./DashboardGrid.module.css";

export default function DashboardGrid({
  cards,
  onOpen,
}: {
  cards: DashboardCard[];
  onOpen: (businessId: string) => void;
}) {
  return (
    <div className={styles.grid}>
      {cards.map((c) => (
        <div
          key={c.business_id}
          className={styles.card}
          onClick={() => onOpen(c.business_id)}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") onOpen(c.business_id);
          }}
        >
          <div className={styles.cardTop}>
            <div>
              <div className={styles.name}>{c.name}</div>
              <div className={styles.id}>{c.business_id}</div>
            </div>
            <RiskPill risk={c.risk} />
          </div>

          <div className={styles.cardBody}>
            <div />
            <ScoreRing value={c.health_score} label="Financial Health" size={92} stroke={10} />
          </div>
        </div>
      ))}
    </div>
  );
}
