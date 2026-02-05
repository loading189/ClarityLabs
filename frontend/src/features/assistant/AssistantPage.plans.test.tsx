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
const getSignalExplain = vi.fn().mockResolvedValue({
  business_id: "biz-1", signal_id: "sig-1",
  state: { status: "open", severity: "warning", created_at: null, updated_at: null, last_seen_at: null, resolved_at: null, metadata: {}, resolved_condition_met: false },
  detector: { type: "expense", title: "Expense creep", description: "", domain: "expense", default_severity: "warning", recommended_actions: [], evidence_schema: [], scoring_profile: {} },
  evidence: [], related_audits: [], next_actions: [], clear_condition: null,
  playbooks: [{ id: "pb-1", title: "Inspect", description: "", kind: "inspect", ui_target: "assistant", deep_link: null }], links: [],
});
const updateSignalStatus = vi.fn();
const listPlans = vi.fn().mockResolvedValue([{ plan_id: "plan-1", business_id: "biz-1", title: "Plan 1", status: "open", created_at: new Date().toISOString(), updated_at: new Date().toISOString(), signal_ids: ["sig-1"], steps: [{ step_id: "step-1", title: "Inspect", status: "todo", playbook_id: "pb-1" }], notes: [] }]);
const createPlan = vi.fn().mockResolvedValue({ plan_id: "plan-2", business_id: "biz-1", title: "Plan 2", status: "open", created_at: new Date().toISOString(), updated_at: new Date().toISOString(), signal_ids: ["sig-1"], steps: [], notes: [] });
const markPlanStepDone = vi.fn().mockResolvedValue({});
const addPlanNote = vi.fn().mockResolvedValue({});
const getMonitorStatus = vi.fn();
const fetchAssistantProgress = vi.fn().mockResolvedValue({ business_id: "biz-1", window_days: 7, generated_at: new Date().toISOString(), health_score: { current: 78, delta_window: 0 }, open_signals: { current: 1, delta_window: 0 }, plans: { active_count: 1, completed_count_window: 0 }, streak_days: 1, top_domains_open: [{ domain: "expense", count: 1 }] });

const fetchWorkQueue = vi.fn().mockResolvedValue({ business_id: "biz-1", generated_at: new Date().toISOString(), items: [] });
vi.mock("../../api/signals", () => ({ listSignalStates: (...args: unknown[]) => listSignalStates(...args), getSignalExplain: (...args: unknown[]) => getSignalExplain(...args), updateSignalStatus: (...args: unknown[]) => updateSignalStatus(...args) }));
vi.mock("../../api/healthScore", () => ({ fetchHealthScore: (...args: unknown[]) => fetchHealthScore(...args), fetchHealthScoreExplainChange: (...args: unknown[]) => fetchHealthScoreExplainChange(...args) }));
vi.mock("../../api/changes", () => ({ listChanges: (...args: unknown[]) => listChanges(...args) }));
vi.mock("../../api/assistantThread", () => ({ fetchAssistantThread: (...args: unknown[]) => fetchAssistantThread(...args), postAssistantMessage: (...args: unknown[]) => postAssistantMessage(...args) }));
vi.mock("../../api/dailyBrief", () => ({ publishDailyBrief: (...args: unknown[]) => publishDailyBrief(...args) }));
vi.mock("../../api/progress", () => ({ fetchAssistantProgress: (...args: unknown[]) => fetchAssistantProgress(...args) }));
vi.mock("../../api/workQueue", () => ({ fetchWorkQueue: (...args: unknown[]) => fetchWorkQueue(...args) }));
vi.mock("../../api/plans", () => ({ listPlans: (...args: unknown[]) => listPlans(...args), createPlan: (...args: unknown[]) => createPlan(...args), markPlanStepDone: (...args: unknown[]) => markPlanStepDone(...args), addPlanNote: (...args: unknown[]) => addPlanNote(...args), updatePlanStatus: (...args: unknown[]) => updatePlanStatus(...args), verifyPlan: (...args: unknown[]) => verifyPlan(...args) }));
vi.mock("../../api/monitor", () => ({ getMonitorStatus: (...args: unknown[]) => getMonitorStatus(...args) }));

function renderAssistant() {
  return render(<AppStateProvider><MemoryRouter initialEntries={["/app/biz-1/assistant"]}><Routes><Route path="/app/:businessId/assistant" element={<AssistantPage />} /></Routes></MemoryRouter></AppStateProvider>);
}

describe("AssistantPage plans", () => {
  afterEach(() => cleanup());
  beforeEach(() => vi.clearAllMocks());

  it("renders plans list", async () => {
    renderAssistant();
    await screen.findByRole("button", { name: /Plan 1 · open/i });
    expect(listPlans).toHaveBeenCalled();
  });

  it("creates plan from daily brief priority click", async () => {
    renderAssistant();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Create plan/i }));
    await waitFor(() => expect(createPlan).toHaveBeenCalled());
  });

  it("marks step done and adds note", async () => {
    renderAssistant();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("checkbox"));
    await waitFor(() => expect(markPlanStepDone).toHaveBeenCalled());
    const textareas = screen.getAllByRole("textbox");
    await user.type(textareas[textareas.length - 1], "note text");
    await user.click(screen.getByRole("button", { name: /Add note/i }));
    await waitFor(() => expect(addPlanNote).toHaveBeenCalled());
    expect(getMonitorStatus).not.toHaveBeenCalled();
  });
});
