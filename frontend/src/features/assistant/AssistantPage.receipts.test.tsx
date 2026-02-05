import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AppStateProvider } from "../../app/state/appState";
import AssistantPage from "./AssistantPage";

const fetchAssistantThread = vi.fn().mockResolvedValue([
  {
    id: "msg-r1",
    business_id: "biz-1",
    created_at: new Date().toISOString(),
    author: "system",
    kind: "receipt_signal_status_updated",
    signal_id: "sig-1",
    audit_id: "audit-1",
    content_json: { action: "signal_status_updated", links: { audit: "/app/biz-1/audit/audit-1", signal: "/app/biz-1/assistant?signalId=sig-1" } },
  },
]);

vi.mock("../../api/assistantThread", () => ({
  fetchAssistantThread: (...args: unknown[]) => fetchAssistantThread(...args),
  postAssistantMessage: vi.fn().mockResolvedValue({}),
}));
vi.mock("../../api/signals", () => ({ listSignalStates: vi.fn().mockResolvedValue({ signals: [], meta: {} }), getSignalExplain: vi.fn(), updateSignalStatus: vi.fn() }));
vi.mock("../../api/healthScore", () => ({ fetchHealthScore: vi.fn().mockResolvedValue({ score: 80, contributors: [] }), fetchHealthScoreExplainChange: vi.fn().mockResolvedValue({ summary: { headline: "", top_drivers: [] }, impacts: [] }) }));
vi.mock("../../api/changes", () => ({ listChanges: vi.fn().mockResolvedValue([]) }));
vi.mock("../../api/dailyBrief", () => ({ publishDailyBrief: vi.fn().mockResolvedValue({ brief: null }) }));
vi.mock("../../api/progress", () => ({ fetchAssistantProgress: vi.fn().mockResolvedValue(null) }));
vi.mock("../../api/workQueue", () => ({ fetchWorkQueue: vi.fn().mockResolvedValue({ items: [] }) }));
vi.mock("../../api/plans", () => ({ listPlans: vi.fn().mockResolvedValue([]), createPlan: vi.fn(), markPlanStepDone: vi.fn(), addPlanNote: vi.fn(), updatePlanStatus: vi.fn(), verifyPlan: vi.fn() }));

function renderAssistant() {
  return render(
    <AppStateProvider>
      <MemoryRouter initialEntries={["/app/biz-1/assistant"]}>
        <Routes>
          <Route path="/app/:businessId/assistant" element={<AssistantPage />} />
        </Routes>
      </MemoryRouter>
    </AppStateProvider>
  );
}

describe("AssistantPage receipts", () => {
  afterEach(() => cleanup());
  beforeEach(() => vi.clearAllMocks());

  it("renders receipt card with audit link", async () => {
    renderAssistant();
    await waitFor(() => expect(fetchAssistantThread).toHaveBeenCalled());
    expect(await screen.findByText(/Receipt:/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Audit audit-1/i })).toBeInTheDocument();
  });
});
