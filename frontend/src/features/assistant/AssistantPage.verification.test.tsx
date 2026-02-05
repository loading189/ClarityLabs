import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AppStateProvider } from "../../app/state/appState";
import AssistantPage from "./AssistantPage";

const getSignalExplain = vi.fn().mockResolvedValue({
  business_id: "biz-1",
  signal_id: "sig-1",
  state: { status: "open", severity: "warning", created_at: null, updated_at: null, last_seen_at: null, resolved_at: null, metadata: {}, resolved_condition_met: false },
  detector: { type: "expense", title: "Expense creep", description: "", domain: "expense", default_severity: "warning", recommended_actions: [], evidence_schema: [], scoring_profile: {} },
  evidence: [],
  related_audits: [],
  next_actions: [],
  clear_condition: { summary: "Spend must normalize.", type: "threshold", fields: ["current_total"], window_days: 14, comparator: "<=", target: 500 },
  verification: { status: "unknown", checked_at: new Date().toISOString(), facts: [] },
  playbooks: [],
  links: [],
});
const verifyPlan = vi.fn().mockResolvedValue({ plan_id: "plan-1", checked_at: new Date().toISOString(), signals: [{ signal_id: "sig-1", verification_status: "met", title: "Expense creep", domain: "expense" }], totals: { met: 1, not_met: 0, unknown: 0 } });

vi.mock("../../api/signals", () => ({
  listSignalStates: vi.fn().mockResolvedValue({ signals: [{ id: "sig-1", type: "expense", domain: "expense", severity: "warning", status: "open", title: "Expense creep", summary: null, updated_at: null }], meta: {} }),
  getSignalExplain: (...args: unknown[]) => getSignalExplain(...args),
  updateSignalStatus: vi.fn(),
}));
vi.mock("../../api/assistantThread", () => ({ fetchAssistantThread: vi.fn().mockResolvedValue([]), postAssistantMessage: vi.fn().mockResolvedValue({}) }));
vi.mock("../../api/healthScore", () => ({ fetchHealthScore: vi.fn().mockResolvedValue({ score: 80, contributors: [] }), fetchHealthScoreExplainChange: vi.fn().mockResolvedValue({ summary: { headline: "", top_drivers: [] }, impacts: [] }) }));
vi.mock("../../api/changes", () => ({ listChanges: vi.fn().mockResolvedValue([]) }));
vi.mock("../../api/dailyBrief", () => ({ publishDailyBrief: vi.fn().mockResolvedValue({ brief: null }) }));
vi.mock("../../api/progress", () => ({ fetchAssistantProgress: vi.fn().mockResolvedValue(null) }));
vi.mock("../../api/workQueue", () => ({ fetchWorkQueue: vi.fn().mockResolvedValue({ items: [] }) }));
vi.mock("../../api/plans", () => ({
  listPlans: vi.fn().mockResolvedValue([{ plan_id: "plan-1", business_id: "biz-1", title: "Plan", status: "open", created_at: new Date().toISOString(), updated_at: new Date().toISOString(), signal_ids: ["sig-1"], steps: [], notes: [] }]),
  createPlan: vi.fn(), markPlanStepDone: vi.fn(), addPlanNote: vi.fn(), updatePlanStatus: vi.fn(), verifyPlan: (...args: unknown[]) => verifyPlan(...args),
}));

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

describe("AssistantPage verification", () => {
  afterEach(() => cleanup());
  beforeEach(() => vi.clearAllMocks());

  it("renders explain verification badge and plan verify totals", async () => {
    renderAssistant();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /1\. Expense creep/i }));
    expect(await screen.findByText(/Verification: Unknown/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Verify plan/i }));
    await waitFor(() => expect(verifyPlan).toHaveBeenCalledWith("biz-1", "plan-1"));
    expect(await screen.findByText(/Met 1 · Not met 0 · Unknown 0/i)).toBeInTheDocument();
  });
});
