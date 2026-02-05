import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Outlet } from "react-router-dom";
import { AppStateProvider } from "../state/appState";
import AppRoutes from "./AppRoutes";

const fetchDashboard = vi.fn().mockResolvedValue({ cards: [{ business_id: "11111111-1111-4111-8111-111111111111" }] });
const fetchBusinessDashboard = vi
  .fn()
  .mockResolvedValue({ metadata: { business_id: "11111111-1111-4111-8111-111111111111" } });

vi.mock("../../api/demo", () => ({
  fetchDashboard: (...args: unknown[]) => fetchDashboard(...args),
  fetchBusinessDashboard: (...args: unknown[]) => fetchBusinessDashboard(...args),
}));

vi.mock("../layout/AppLayout", () => ({
  default: () => (
    <div data-testid="layout-shell">
      <span>layout</span>
      <Outlet />
    </div>
  ),
}));

vi.mock("./AssistantPage", () => ({ default: () => <div>assistant-page</div> }));
vi.mock("./DashboardPage", () => ({ default: () => <div>dashboard-page</div> }));
vi.mock("./SignalsCenterPage", () => ({ default: () => <div>signals-page</div> }));
vi.mock("../../features/ledger/LedgerPage", () => ({ default: () => <div>ledger-page</div> }));
vi.mock("../../features/trends/TrendsPage", () => ({ default: () => <div>trends-page</div> }));
vi.mock("./VendorsPage", () => ({ default: () => <div>vendors-page</div> }));
vi.mock("./CategorizePage", () => ({ default: () => <div>categorize-page</div> }));
vi.mock("./RulesPage", () => ({ default: () => <div>rules-page</div> }));
vi.mock("./IntegrationsPage", () => ({ default: () => <div>integrations-page</div> }));
vi.mock("./SettingsPage", () => ({ default: () => <div>settings-page</div> }));
vi.mock("./AdminSimulatorPage", () => ({ default: () => <div>admin-page</div> }));
vi.mock("./BusinessSelectPage", () => ({ default: () => <div>business-select-page</div> }));
vi.mock("./OnboardingWizardPage", () => ({ default: () => <div>onboarding-page</div> }));


afterEach(() => {
  cleanup();
});

function renderRoutes(path: string) {
  return render(
    <AppStateProvider>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </AppStateProvider>
  );
}

describe("AppRoutes redirects", () => {
  it("redirects workspace home to assistant", async () => {
    renderRoutes("/app/11111111-1111-4111-8111-111111111111/home");
    await waitFor(() => expect(screen.getAllByText("assistant-page").length).toBeGreaterThan(0));
  });

  it("redirects workspace health to assistant", async () => {
    renderRoutes("/app/11111111-1111-4111-8111-111111111111/health");
    await waitFor(() => expect(screen.getAllByText("assistant-page").length).toBeGreaterThan(0));
  });

  it("redirects top-level assistant compatibility route", async () => {
    renderRoutes("/assistant?businessId=11111111-1111-4111-8111-111111111111&signalId=sig-1");
    await waitFor(() => expect(screen.getAllByText("assistant-page").length).toBeGreaterThan(0));
  });

  it("redirects /app to assistant default route", async () => {
    renderRoutes("/app");
    await waitFor(() => expect(fetchDashboard).toHaveBeenCalled());
    await waitFor(() => expect(screen.getAllByText("assistant-page").length).toBeGreaterThan(0));
  });

  it("redirects /app/:businessId to assistant", async () => {
    renderRoutes("/app/11111111-1111-4111-8111-111111111111");
    await waitFor(() => expect(screen.getAllByText("assistant-page").length).toBeGreaterThan(0));
  });
});
