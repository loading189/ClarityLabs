import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AppStateProvider } from "../../app/state/appState";
import AssistantPage from "./AssistantPage";

const fetchAssistantSummary = vi.fn();
const fetchActionTriage = vi.fn();
const getActions = vi.fn();
const getAuditLog = vi.fn();

vi.mock("../../api/assistantTools", () => ({
  fetchAssistantSummary: (...args: unknown[]) => fetchAssistantSummary(...args),
}));
vi.mock("../../api/actions", () => ({
  fetchActionTriage: (...args: unknown[]) => fetchActionTriage(...args),
  getActions: (...args: unknown[]) => getActions(...args),
}));
vi.mock("../../api/audit", () => ({
  getAuditLog: (...args: unknown[]) => getAuditLog(...args),
}));
vi.mock("../../app/auth/AuthContext", () => ({
  useAuth: () => ({ logout: vi.fn() }),
}));

function renderSummary(path = "/app/biz-1/summary") {
  return render(
    <AppStateProvider>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/app/:businessId/summary" element={<AssistantPage />} />
        </Routes>
      </MemoryRouter>
    </AppStateProvider>
  );
}

describe("AssistantPage (Summary)", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders counts and links for summary navigation", async () => {
    fetchAssistantSummary.mockResolvedValue({
      business_id: "biz-1",
      integrations: [],
      monitor_status: { stale: false, gated: false },
      open_signals: 3,
      uncategorized_count: 2,
      audit_events: [],
      top_vendors: [],
    });
    fetchActionTriage.mockResolvedValue({ actions: [{ id: "a1" }], summary: { by_status: {}, by_business: [] } });
    getActions.mockResolvedValue({ actions: [] });
    getAuditLog.mockResolvedValue({ items: [] });

    renderSummary();

    await waitFor(() => expect(fetchAssistantSummary).toHaveBeenCalled());
    expect(screen.getByText("Open actions")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();

    const inboxLink = screen.getByRole("link", { name: /View inbox/i });
    expect(inboxLink).toHaveAttribute("href", "/app/biz-1/advisor?status=open");

    const signalsLink = screen.getByRole("link", { name: /Review evidence/i });
    expect(signalsLink).toHaveAttribute("href", "/app/biz-1/signals?status=open");
  });

  it("does not render inbox-style work controls", async () => {
    fetchAssistantSummary.mockResolvedValue({
      business_id: "biz-1",
      integrations: [],
      monitor_status: { stale: false, gated: false },
      open_signals: 0,
      uncategorized_count: 0,
      audit_events: [],
      top_vendors: [],
    });
    fetchActionTriage.mockResolvedValue({ actions: [], summary: { by_status: {}, by_business: [] } });
    getActions.mockResolvedValue({ actions: [] });
    getAuditLog.mockResolvedValue({ items: [] });

    renderSummary();

    await waitFor(() => expect(fetchAssistantSummary).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: /Refresh Actions/i })).not.toBeInTheDocument();
    expect(screen.queryByText("Assigned to me")).not.toBeInTheDocument();
  });
});
