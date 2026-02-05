import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AppStateProvider } from "../../app/state/appState";
import AssistantPage from "./AssistantPage";

const listSignalStates = vi.fn().mockResolvedValue({
  signals: [{ id: "sig-1", type: "expense", domain: "expense", severity: "warning", status: "open", title: "Expense creep", summary: null, updated_at: null }],
  meta: {},
});
const fetchHealthScore = vi.fn().mockResolvedValue({ business_id: "biz-1", score: 78, generated_at: new Date().toISOString(), domains: [], contributors: [], meta: { model_version: "v1", weights: {} } });
const fetchHealthScoreExplainChange = vi.fn().mockResolvedValue({ business_id: "biz-1", computed_at: new Date().toISOString(), window: { since_hours: 72 }, changes: [], impacts: [], summary: { headline: "No major changes", net_estimated_delta: 0, top_drivers: [] } });
const listChanges = vi.fn().mockResolvedValue([]);
const fetchAssistantThread = vi.fn().mockResolvedValue([]);
const postAssistantMessage = vi.fn().mockResolvedValue({});
const publishDailyBrief = vi.fn().mockResolvedValue({
  message: {},
  brief: {
    business_id: "biz-1",
    date: "2025-01-15",
    generated_at: new Date().toISOString(),
    headline: "Daily brief headline",
    summary_bullets: ["Health score is 78."],
    priorities: [{ signal_id: "sig-1", title: "Expense creep", severity: "warning", status: "open", why_now: "Expense creep is open.", recommended_playbooks: [], clear_condition_summary: "Spend normalize." }],
    metrics: { health_score: 78, delta_7d: null, open_signals_count: 1, new_changes_count: 0 },
    links: { assistant: "/", signals: "/", health_score: "/", changes: "/" },
  },
});
const fetchAssistantProgress = vi.fn().mockResolvedValue({
  business_id: "biz-1",
  window_days: 7,
  generated_at: new Date().toISOString(),
  health_score: { current: 78, delta_window: 2 },
  open_signals: { current: 3, delta_window: -1 },
  plans: { active_count: 2, completed_count_window: 1 },
  streak_days: 4,
  top_domains_open: [{ domain: "expense", count: 2 }, { domain: "liquidity", count: 1 }],
});
const getSignalExplain = vi.fn().mockResolvedValue({
  business_id: "biz-1", signal_id: "sig-1",
  state: { status: "open", severity: "warning", created_at: null, updated_at: null, last_seen_at: null, resolved_at: null, metadata: {}, resolved_condition_met: false },
  detector: { type: "expense", title: "Expense creep", description: "", domain: "expense", default_severity: "warning", recommended_actions: [], evidence_schema: [], scoring_profile: {} },
  evidence: [], related_audits: [], next_actions: [], clear_condition: null, playbooks: [], links: [],
});
const updateSignalStatus = vi.fn();
const listPlans = vi.fn().mockResolvedValue([{ plan_id: "plan-1", business_id: "biz-1", title: "Plan 1", status: "done", created_at: new Date().toISOString(), updated_at: new Date().toISOString(), signal_ids: ["sig-1"], steps: [], notes: [], outcome: { health_score_at_start: 75, health_score_at_done: 78, health_score_delta: 3, signals_total: 1, signals_resolved_count: 1, signals_still_open_count: 0, summary_bullets: ["Signals resolved: 1/1.", "Signals still open: 0.", "Health score changed by +3.00.", "Clear-condition checks met: 0/1."] } }]);
const createPlan = vi.fn();
const markPlanStepDone = vi.fn();
const addPlanNote = vi.fn();
const updatePlanStatus = vi.fn().mockResolvedValue({});
const getMonitorStatus = vi.fn();

vi.mock("../../api/signals", () => ({ listSignalStates: (...args: unknown[]) => listSignalStates(...args), getSignalExplain: (...args: unknown[]) => getSignalExplain(...args), updateSignalStatus: (...args: unknown[]) => updateSignalStatus(...args) }));
vi.mock("../../api/healthScore", () => ({ fetchHealthScore: (...args: unknown[]) => fetchHealthScore(...args), fetchHealthScoreExplainChange: (...args: unknown[]) => fetchHealthScoreExplainChange(...args) }));
vi.mock("../../api/changes", () => ({ listChanges: (...args: unknown[]) => listChanges(...args) }));
vi.mock("../../api/assistantThread", () => ({ fetchAssistantThread: (...args: unknown[]) => fetchAssistantThread(...args), postAssistantMessage: (...args: unknown[]) => postAssistantMessage(...args) }));
vi.mock("../../api/dailyBrief", () => ({ publishDailyBrief: (...args: unknown[]) => publishDailyBrief(...args) }));
vi.mock("../../api/progress", () => ({ fetchAssistantProgress: (...args: unknown[]) => fetchAssistantProgress(...args) }));
vi.mock("../../api/plans", () => ({ listPlans: (...args: unknown[]) => listPlans(...args), createPlan: (...args: unknown[]) => createPlan(...args), markPlanStepDone: (...args: unknown[]) => markPlanStepDone(...args), addPlanNote: (...args: unknown[]) => addPlanNote(...args), updatePlanStatus: (...args: unknown[]) => updatePlanStatus(...args) }));
vi.mock("../../api/monitor", () => ({ getMonitorStatus: (...args: unknown[]) => getMonitorStatus(...args) }));

function renderAssistant() {
  return render(<AppStateProvider><MemoryRouter initialEntries={["/app/biz-1/assistant"]}><Routes><Route path="/app/:businessId/assistant" element={<AssistantPage />} /></Routes></MemoryRouter></AppStateProvider>);
}

describe("AssistantPage progress", () => {
  afterEach(() => cleanup());
  beforeEach(() => vi.clearAllMocks());

  it("renders progress panel", async () => {
    renderAssistant();
    await screen.findByText(/Progress/i);
    expect(screen.getByText(/Health score 78/)).toBeInTheDocument();
    expect(fetchAssistantProgress).toHaveBeenCalled();
  });

  it("renders plan outcome when done", async () => {
    renderAssistant();
    await screen.findByText(/Outcome/i);
    expect(screen.getByText(/Signals resolved 1\/1/)).toBeInTheDocument();
    expect(getMonitorStatus).not.toHaveBeenCalled();
  });

  it("marks plan done", async () => {
    renderAssistant();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Mark done/i }));
    await waitFor(() => expect(updatePlanStatus).toHaveBeenCalled());
  });
});
