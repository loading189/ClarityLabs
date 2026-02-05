import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AppStateProvider } from "../../app/state/appState";
import AssistantPage from "./AssistantPage";

const listSignalStates = vi.fn().mockResolvedValue({ signals: [], meta: {} });
const fetchHealthScore = vi.fn().mockResolvedValue({ business_id: "biz-1", score: 70, generated_at: new Date().toISOString(), domains: [], contributors: [], meta: { model_version: "v1", weights: {} } });
const fetchHealthScoreExplainChange = vi.fn().mockResolvedValue({ business_id: "biz-1", computed_at: new Date().toISOString(), window: { since_hours: 72 }, changes: [], impacts: [], summary: { headline: "No major changes", net_estimated_delta: 0, top_drivers: [] } });
const listChanges = vi.fn().mockResolvedValue([]);
const fetchAssistantThread = vi.fn().mockResolvedValue([]);
const postAssistantMessage = vi.fn().mockResolvedValue({});
const publishDailyBrief = vi.fn().mockResolvedValue({ message: {}, brief: { business_id: "biz-1", date: "2025-01-01", generated_at: new Date().toISOString(), headline: "Headline", summary_bullets: [], priorities: [], metrics: { health_score: 70, delta_7d: 0, open_signals_count: 2, new_changes_count: 0 }, links: { assistant: "/", signals: "/", health_score: "/", changes: "/" } } });
const getSignalExplain = vi.fn().mockResolvedValue({ business_id: "biz-1", signal_id: "sig-2", state: { status: "open", severity: "critical", created_at: null, updated_at: null, last_seen_at: null, resolved_at: null, metadata: {}, resolved_condition_met: false }, detector: { type: "x", title: "Signal", description: "", domain: "liquidity", default_severity: "critical", recommended_actions: [], evidence_schema: [], scoring_profile: {} }, evidence: [], related_audits: [], next_actions: [], clear_condition: null, playbooks: [], links: [] });
const updateSignalStatus = vi.fn();
const listPlans = vi.fn();
const createPlan = vi.fn();
const markPlanStepDone = vi.fn();
const addPlanNote = vi.fn();
const updatePlanStatus = vi.fn();
const fetchAssistantProgress = vi.fn().mockResolvedValue({ business_id: "biz-1", window_days: 7, generated_at: new Date().toISOString(), health_score: { current: 70, delta_window: 0 }, open_signals: { current: 2, delta_window: 0 }, plans: { active_count: 1, completed_count_window: 0 }, streak_days: 1, top_domains_open: [{ domain: "liquidity", count: 2 }] });
const getMonitorStatus = vi.fn();
const fetchWorkQueue = vi.fn();

vi.mock("../../api/signals", () => ({ listSignalStates: (...args: unknown[]) => listSignalStates(...args), getSignalExplain: (...args: unknown[]) => getSignalExplain(...args), updateSignalStatus: (...args: unknown[]) => updateSignalStatus(...args) }));
vi.mock("../../api/healthScore", () => ({ fetchHealthScore: (...args: unknown[]) => fetchHealthScore(...args), fetchHealthScoreExplainChange: (...args: unknown[]) => fetchHealthScoreExplainChange(...args) }));
vi.mock("../../api/changes", () => ({ listChanges: (...args: unknown[]) => listChanges(...args) }));
vi.mock("../../api/assistantThread", () => ({ fetchAssistantThread: (...args: unknown[]) => fetchAssistantThread(...args), postAssistantMessage: (...args: unknown[]) => postAssistantMessage(...args) }));
vi.mock("../../api/dailyBrief", () => ({ publishDailyBrief: (...args: unknown[]) => publishDailyBrief(...args) }));
vi.mock("../../api/plans", () => ({ listPlans: (...args: unknown[]) => listPlans(...args), createPlan: (...args: unknown[]) => createPlan(...args), markPlanStepDone: (...args: unknown[]) => markPlanStepDone(...args), addPlanNote: (...args: unknown[]) => addPlanNote(...args), updatePlanStatus: (...args: unknown[]) => updatePlanStatus(...args) }));
vi.mock("../../api/progress", () => ({ fetchAssistantProgress: (...args: unknown[]) => fetchAssistantProgress(...args) }));
vi.mock("../../api/monitor", () => ({ getMonitorStatus: (...args: unknown[]) => getMonitorStatus(...args) }));
vi.mock("../../api/workQueue", () => ({ fetchWorkQueue: (...args: unknown[]) => fetchWorkQueue(...args) }));

function renderAssistant(path = "/app/biz-1/assistant") {
  return render(<AppStateProvider><MemoryRouter initialEntries={[path]}><Routes><Route path="/app/:businessId/assistant" element={<AssistantPage />} /></Routes></MemoryRouter></AppStateProvider>);
}

describe("AssistantPage work queue", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    vi.clearAllMocks();
    listPlans.mockResolvedValue([]);
    fetchWorkQueue.mockResolvedValue({
      business_id: "biz-1",
      generated_at: new Date().toISOString(),
      items: [
        { kind: "signal", id: "sig-1", title: "Critical cash", severity: "critical", status: "open", domain: "liquidity", score: 120, why_now: "critical; no plan.", primary_action: { label: "Open Explain", type: "open_explain", payload: { signal_id: "sig-1" } }, links: { assistant: "/" } },
        { kind: "plan", id: "plan-1", title: "Plan one", status: "open", domain: "assistant", score: 92, why_now: "active plan", primary_action: { label: "Open Plan", type: "open_plan", payload: { plan_id: "plan-1" } }, links: { assistant: "/" } },
        { kind: "signal", id: "sig-2", title: "Revenue dip", severity: "warning", status: "open", domain: "revenue", score: 75, why_now: "warning", primary_action: { label: "Open Explain", type: "open_explain", payload: { signal_id: "sig-2" } }, links: { assistant: "/" } },
        { kind: "signal", id: "sig-3", title: "Backlog item", severity: "info", status: "open", domain: "expense", score: 20, why_now: "info", primary_action: { label: "Open Explain", type: "open_explain", payload: { signal_id: "sig-3" } }, links: { assistant: "/" } },
      ],
    });
  });

  it("renders top 3 in Do next", async () => {
    renderAssistant();
    await screen.findByText("Today's Work Queue");
    expect(screen.getByText("Critical cash")).toBeInTheDocument();
    expect(screen.getByText("Plan one")).toBeInTheDocument();
    expect(screen.getByText("Revenue dip")).toBeInTheDocument();
    expect(screen.getByText("Backlog item")).toBeInTheDocument();
  });

  it("clicking queue item triggers expected behavior", async () => {
    renderAssistant();
    const user = userEvent.setup();
    const openExplainButtons = await screen.findAllByRole("button", { name: /Open Explain/i });
    await user.click(openExplainButtons[0]);
    await waitFor(() => expect(getSignalExplain).toHaveBeenCalled());
  });

  it("resume selects active plan before signal", async () => {
    listPlans.mockResolvedValue([{ plan_id: "plan-1", business_id: "biz-1", title: "Plan one", status: "open", created_at: new Date().toISOString(), updated_at: new Date().toISOString(), signal_ids: ["sig-1"], steps: [{ step_id: "step-1", title: "Do x", status: "todo", playbook_id: "pb-1" }], notes: [] }]);
    renderAssistant();
    await screen.findByText(/Plan one · open/i);
    expect(getSignalExplain).not.toHaveBeenCalledWith("biz-1", "sig-1");
  });

  it("does not call monitor status", async () => {
    renderAssistant();
    await screen.findByText("Today's Work Queue");
    expect(getMonitorStatus).not.toHaveBeenCalled();
  });
});
