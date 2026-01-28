import ScoreRing from "./ScoreRing";
import RiskPill from "./RiskPill";
import type { DashboardCard } from "../types";

export default function DashboardGrid({
  cards,
  onOpen,
}: {
  cards: DashboardCard[];
  onOpen: (businessId: string) => void;
}) {
  return (
    <div className="grid">
      {cards.map((c) => (
        <div
          key={c.business_id}
          className="card"
          onClick={() => onOpen(c.business_id)}
          style={{ cursor: "pointer" }}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") onOpen(c.business_id);
          }}
        >
          <div className="cardTop">
            <div>
              <div className="name">{c.name}</div>
              <div className="id">{c.business_id}</div>
            </div>
            <RiskPill risk={c.risk} />
          </div>

          <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "center" }}>
            <div>
            </div>
            <ScoreRing value={c.health_score} label="Financial Health" size={92} stroke={10} />
          </div>
        </div>
      ))}
    </div>
  );
}
