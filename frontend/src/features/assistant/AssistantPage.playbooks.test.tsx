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
const fetchHealthScore = vi.fn().mockResolvedValue({ business_id: "biz-1", score: 78, generated_at: new Date().toISOString(), domains: [], contributors: [{ signal_id: "sig-1", domain: "expense", status: "open", severity: "warning", penalty: 12, rationale: "" }], meta: { model_version: "v1", weights: {} } });
const fetchHealthScoreExplainChange = vi.fn().mockResolvedValue({ business_id: "biz-1", computed_at: new Date().toISOString(), window: { since_hours: 72 }, changes: [], impacts: [], summary: { headline: "No major changes", net_estimated_delta: 0, top_drivers: [] } });
const listChanges = vi.fn().mockResolvedValue([]);
const fetchAssistantThread = vi.fn().mockResolvedValue([]);
const postAssistantMessage = vi.fn().mockResolvedValue({ id: "msg-1", business_id: "biz-1", created_at: new Date().toISOString(), author: "assistant", kind: "summary", signal_id: null, audit_id: null, content_json: { text: "ok" } });
const getSignalExplain = vi.fn().mockResolvedValue({
  business_id: "biz-1",
  signal_id: "sig-1",
  state: { status: "open", severity: "warning", created_at: null, updated_at: null, last_seen_at: null, resolved_at: null, metadata: {}, resolved_condition_met: false },
  detector: { type: "expense", title: "Expense creep", description: "", domain: "expense", default_severity: "warning", recommended_actions: [], evidence_schema: [], scoring_profile: {} },
  evidence: [],
  related_audits: [],
  next_actions: [{ key: "resolve_if_fixed", label: "Resolve", action: "resolve", requires_reason: true, rationale: "", suggested_snooze_minutes: null, guardrails: [] }],
  clear_condition: { summary: "Spend must normalize.", type: "threshold", fields: ["current_total"], window_days: 14, comparator: "<=", target: 500 },
  playbooks: [{ id: "expense_inspect_ledger", title: "Inspect recent outflows", description: "Review ledger", kind: "inspect", ui_target: "ledger", deep_link: null, requires_confirmation: false }],
  links: [],
});
const updateSignalStatus = vi.fn().mockResolvedValue({ business_id: "biz-1", signal_id: "sig-1", status: "resolved", last_seen_at: null, resolved_at: null, resolution_note: "done", reason: "done", audit_id: "audit-1" });
const getMonitorStatus = vi.fn();
const fetchAssistantProgress = vi.fn().mockResolvedValue({ business_id: "biz-1", window_days: 7, generated_at: new Date().toISOString(), health_score: { current: 78, delta_window: 0 }, open_signals: { current: 1, delta_window: 0 }, plans: { active_count: 1, completed_count_window: 0 }, streak_days: 1, top_domains_open: [{ domain: "expense", count: 1 }] });
const listPlans = vi.fn().mockResolvedValue([]);
const createPlan = vi.fn();
const markPlanStepDone = vi.fn();
const addPlanNote = vi.fn();
const publishDailyBrief = vi.fn().mockResolvedValue({
  message: { id: "msg-brief", business_id: "biz-1", created_at: new Date().toISOString(), author: "system", kind: "daily_brief", signal_id: null, audit_id: null, content_json: {} },
  brief: {
    business_id: "biz-1",
    date: "2025-01-15",
    generated_at: new Date().toISOString(),
    headline: "Daily brief headline",
    summary_bullets: ["Health score is 78."],
    priorities: [{ signal_id: "sig-1", title: "Expense creep", severity: "warning", status: "open", why_now: "Expense creep is open with warning severity.", recommended_playbooks: [{ id: "pb-1", title: "Inspect recent outflows", deep_link: null }], clear_condition_summary: "Spend must normalize." }],
    metrics: { health_score: 78, delta_7d: -12, open_signals_count: 1, new_changes_count: 1 },
    links: { assistant: "/", signals: "/", health_score: "/", changes: "/" },
  },
});

const fetchWorkQueue = vi.fn().mockResolvedValue({ business_id: "biz-1", generated_at: new Date().toISOString(), items: [] });
vi.mock("../../api/signals", () => ({
  listSignalStates: (...args: unknown[]) => listSignalStates(...args),
  getSignalExplain: (...args: unknown[]) => getSignalExplain(...args),
  updateSignalStatus: (...args: unknown[]) => updateSignalStatus(...args),
}));
vi.mock("../../api/healthScore", () => ({
  fetchHealthScore: (...args: unknown[]) => fetchHealthScore(...args),
  fetchHealthScoreExplainChange: (...args: unknown[]) => fetchHealthScoreExplainChange(...args),
}));
vi.mock("../../api/changes", () => ({ listChanges: (...args: unknown[]) => listChanges(...args) }));
vi.mock("../../api/assistantThread", () => ({
  fetchAssistantThread: (...args: unknown[]) => fetchAssistantThread(...args),
  postAssistantMessage: (...args: unknown[]) => postAssistantMessage(...args),
}));
vi.mock("../../api/monitor", () => ({ getMonitorStatus: (...args: unknown[]) => getMonitorStatus(...args) }));
vi.mock("../../api/dailyBrief", () => ({ publishDailyBrief: (...args: unknown[]) => publishDailyBrief(...args) }));
vi.mock("../../api/progress", () => ({ fetchAssistantProgress: (...args: unknown[]) => fetchAssistantProgress(...args) }));
vi.mock("../../api/workQueue", () => ({ fetchWorkQueue: (...args: unknown[]) => fetchWorkQueue(...args) }));
vi.mock("../../api/plans", () => ({ listPlans: (...args: unknown[]) => listPlans(...args), createPlan: (...args: unknown[]) => createPlan(...args), markPlanStepDone: (...args: unknown[]) => markPlanStepDone(...args), addPlanNote: (...args: unknown[]) => addPlanNote(...args) }));

function renderAssistant(path = "/app/biz-1/assistant") {
  return render(
    <AppStateProvider>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/app/:businessId/assistant" element={<AssistantPage />} />
        </Routes>
      </MemoryRouter>
    </AppStateProvider>
  );
}

describe("AssistantPage playbooks", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    vi.clearAllMocks();
    fetchAssistantThread.mockResolvedValue([]);
  });

  it("renders clear condition and playbooks, and clicking playbook appends thread message", async () => {
    renderAssistant();
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: /1\. Expense creep/i }));

    await screen.findByText(/What resolves this/i);
    expect(screen.getAllByText(/Spend must normalize\./i).length).toBeGreaterThan(0);
    const playbookBtn = screen.getAllByRole("button", { name: /Inspect recent outflows/i }).find((btn) => btn.textContent?.includes("🔎"));
    expect(playbookBtn).toBeDefined();
    expect(playbookBtn).toBeInTheDocument();

    await user.click(playbookBtn!);

    await waitFor(() =>
      expect(postAssistantMessage).toHaveBeenCalledWith(
        "biz-1",
        expect.objectContaining({ author: "system", kind: "playbook_started", signal_id: "sig-1" })
      )
    );
    expect(getMonitorStatus).not.toHaveBeenCalled();
  });
});
