import "./App.css";
import { useState } from "react";
import { useDashboard } from "./hooks/useDashboard";
import { useBusinessDetail } from "./hooks/useBusinessDetail";
import DetailPanel from "./components/DetailPanel/DetailPanel";
import DashboardGrid from "./components/DashboardGrid";
import Onboarding from "./pages/Onboarding";

import logo from "../public/logo.svg"; // <-- adjust filename if needed

function OnboardingIcon() {
  // simple inline svg (no extra deps)
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M8 7h8M8 11h8M8 15h5"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <path
        d="M6 3h12a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z"
        stroke="currentColor"
        strokeWidth="2"
      />
    </svg>
  );
}

export default function App() {
  const [tab, setTab] = useState<"dashboard" | "onboarding">("dashboard");

  const { cards, err, loading } = useDashboard();
  const detailState = useBusinessDetail();

  if (err) return <div className="page">Error: {err}</div>;
  if (loading) return <div className="page">Loading…</div>;

  return (
    <div className="page">
      <header className="header">
        {/* left brand (logo + name) */}
        <div className="brandRow">
          <img src={logo} alt="Clarity Labs" className="logo" />
          <h1 style={{ margin: 0 }}>Clarity Labs</h1>
        </div>

        {/* right nav (single line) */}
        <div className="navRow">
          <button
            className="closeBtn"
            onClick={() => setTab("dashboard")}
            style={{ opacity: tab === "dashboard" ? 1 : 0.6 }}
          >
            Dashboard
          </button>

          <button
            className="closeBtn"
            onClick={() => setTab("onboarding")}
            style={{ opacity: tab === "onboarding" ? 1 : 0.6, display: "flex", alignItems: "center", gap: 8 }}
            title="Onboarding"
            aria-label="Onboarding"
          >
            <OnboardingIcon />
          </button>
        </div>
      </header>

      <div className="shell">
        {tab === "onboarding" && <Onboarding />}

        <DetailPanel
          state={detailState}
          onAfterPulse={() => {
            // refresh dashboard after sim pulses (optional)
          }}
        />

        {tab === "dashboard" && <DashboardGrid cards={cards} onOpen={detailState.open} />}
      </div>
    </div>
  );
}
