// frontend/src/app/routes/AppRoutes.tsx
import { Navigate, Route, Routes, useSearchParams } from "react-router-dom";
import AppLayout from "../layout/AppLayout";
import AdminSimulatorPage from "./AdminSimulatorPage";
import CategorizePage from "./CategorizePage";
import DashboardPage from "./DashboardPage";
import IntegrationsPage from "./IntegrationsPage";
import LedgerPage from "../../features/ledger/LedgerPage";
import RulesPage from "./RulesPage";
import SignalsCenterPage from "./SignalsCenterPage";
import SettingsPage from "./SettingsPage";
import TrendsPage from "../../features/trends/TrendsPage";
import VendorsPage from "./VendorsPage";
import AppIndexRedirect from "./AppIndexRedirect";
import BusinessSelectPage from "./BusinessSelectPage";
import OnboardingWizardPage from "./OnboardingWizardPage";
import ErrorBoundary from "../../components/common/ErrorBoundary";
import AssistantPage from "./AssistantPage";
import AdvisorInboxPage from "../../pages/AdvisorInboxPage";


function AssistantCompatRedirect() {
  const [searchParams] = useSearchParams();
  const businessId = searchParams.get("businessId")?.trim();
  const signalId = searchParams.get("signalId")?.trim();

  if (!businessId) {
    return <Navigate to="/app" replace />;
  }

  const nextSearch = signalId ? `?signalId=${encodeURIComponent(signalId)}` : "";
  return <Navigate to={`/app/${businessId}/summary${nextSearch}`} replace />;
}

export default function AppRoutes() {
  return (
    <ErrorBoundary>
      <Routes>
        <Route path="/" element={<Navigate to="/app" replace />} />

        {/* entry */}
        <Route path="/app" element={<AppIndexRedirect />} />
        <Route path="/businesses" element={<BusinessSelectPage />} />
        <Route path="/app/select" element={<Navigate to="/businesses" replace />} />
        <Route path="/onboarding" element={<OnboardingWizardPage />} />
        <Route path="/assistant" element={<AssistantCompatRedirect />} />

        {/* workspace */}
        <Route path="/app/:businessId" element={<AppLayout />}>
          <Route index element={<Navigate to="advisor" replace />} />
          <Route path="home" element={<Navigate to="../advisor" replace />} />
          <Route path="health" element={<Navigate to="../advisor" replace />} />
          <Route path="assistant" element={<Navigate to="../summary" replace />} />
          <Route path="summary" element={<AssistantPage />} />
          <Route path="advisor" element={<AdvisorInboxPage />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="signals" element={<SignalsCenterPage />} />
          <Route path="ledger" element={<LedgerPage />} />
          <Route path="trends" element={<TrendsPage />} />
          <Route path="vendors" element={<VendorsPage />} />
          <Route path="categorize" element={<CategorizePage />} />
          <Route path="rules" element={<RulesPage />} />
          <Route path="integrations" element={<IntegrationsPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="admin/simulator" element={<AdminSimulatorPage />} />
          <Route path="*" element={<Navigate to="summary" replace />} />
        </Route>

        <Route path="*" element={<Navigate to="/app" replace />} />
      </Routes>
    </ErrorBoundary>
  );
}
