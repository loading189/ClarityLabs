import { useState } from "react";
import { useDashboard } from "./hooks/useDashboard";
import { useBusinessDetail } from "./hooks/useBusinessDetail";
import DetailPanel from "./components/DetailPanel/DetailPanel";
import DashboardGrid from "./components/DashboardGrid";
import Onboarding from "./pages/Onboarding";
import styles from "./App.module.css";

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

  if (err) return <div className={styles.page}>Error: {err}</div>;
  if (loading) return <div className={styles.page}>Loading…</div>;

  const navButtonClass = (active: boolean) =>
    `${styles.navButton} ${active ? styles.navButtonActive : ""}`;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        {/* left brand (logo + name) */}
        <div className={styles.brandRow}>
          <img src="/logo.svg" alt="Clarity Labs" className={styles.logo} />
          <h1 className={styles.brandTitle}>Clarity Labs</h1>
        </div>

        {/* right nav (single line) */}
        <div className={styles.navRow}>
          <button
            className={navButtonClass(tab === "dashboard")}
            onClick={() => setTab("dashboard")}
            type="button"
          >
            Dashboard
          </button>

          <button
            className={navButtonClass(tab === "onboarding")}
            onClick={() => setTab("onboarding")}
            title="Onboarding"
            aria-label="Onboarding"
            type="button"
          >
            <OnboardingIcon />
          </button>
        </div>
      </header>

      <div className={styles.shell}>
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
