// frontend/src/app/routes/AppRoutes.tsx
import { Navigate, Route, Routes } from "react-router-dom";
import AppLayout from "../layout/AppLayout";
import AdminSimulatorPage from "./AdminSimulatorPage";
import CategorizePage from "./CategorizePage";
import DashboardPage from "./DashboardPage";
import HealthPage from "./HealthPage";
import HomePage from "./HomePage";
import IntegrationsPage from "./IntegrationsPage";
import LedgerPage from "../../features/ledger/LedgerPage";
import RulesPage from "./RulesPage";
import SettingsPage from "./SettingsPage";
import TrendsPage from "../../features/trends/TrendsPage";
import VendorsPage from "./VendorsPage";
import AppIndexRedirect from "./AppIndexRedirect";
import BusinessSelectPage from "./BusinessSelectPage";
import OnboardingWizardPage from "./OnboardingWizardPage";
import ErrorBoundary from "../../components/common/ErrorBoundary";

export default function AppRoutes() {
  return (
    <ErrorBoundary>
      <Routes>
        <Route path="/" element={<Navigate to="/app" replace />} />

        {/* entry */}
        <Route path="/app" element={<AppIndexRedirect />} />
        <Route path="/app/select" element={<BusinessSelectPage />} />
        <Route path="/onboarding" element={<OnboardingWizardPage />} />

        {/* workspace */}
        <Route path="/app/:businessId" element={<AppLayout />}>
          <Route path="home" element={<HomePage />} />
          <Route path="health" element={<HealthPage />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="ledger" element={<LedgerPage />} />
          <Route path="trends" element={<TrendsPage />} />
          <Route path="vendors" element={<VendorsPage />} />
          <Route path="categorize" element={<CategorizePage />} />
          <Route path="rules" element={<RulesPage />} />
          <Route path="integrations" element={<IntegrationsPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="admin/simulator" element={<AdminSimulatorPage />} />
          <Route path="*" element={<Navigate to="dashboard" replace />} />
        </Route>

        <Route path="*" element={<Navigate to="/app" replace />} />
      </Routes>
    </ErrorBoundary>
  );
}
