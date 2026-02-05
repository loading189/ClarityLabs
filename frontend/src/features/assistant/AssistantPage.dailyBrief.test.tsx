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
const postAssistantMessage = vi.fn().mockResolvedValue({ id: "msg-1", business_id: "biz-1", created_at: new Date().toISOString(), author: "assistant", kind: "playbook_started", signal_id: "sig-1", audit_id: null, content_json: {} });
const publishDailyBrief = vi.fn().mockResolvedValue({
  message: { id: "msg-brief", business_id: "biz-1", created_at: new Date().toISOString(), author: "system", kind: "daily_brief", signal_id: null, audit_id: null, content_json: {} },
  brief: {
    business_id: "biz-1",
    date: "2025-01-15",
    generated_at: new Date().toISOString(),
    headline: "Daily brief for 2025-01-15: health score 78 with 1 active priorities.",
    summary_bullets: ["Health score is 78."],
    priorities: [{ signal_id: "sig-1", title: "Expense creep", severity: "warning", status: "open", why_now: "Expense creep is open with warning severity.", recommended_playbooks: [{ id: "pb-1", title: "Inspect recent outflows", deep_link: null }], clear_condition_summary: "Spend must normalize." }],
    metrics: { health_score: 78, delta_7d: null, open_signals_count: 1, new_changes_count: 0 },
    links: { assistant: "/", signals: "/", health_score: "/", changes: "/" },
  },
});
const getSignalExplain = vi.fn().mockResolvedValue({
  business_id: "biz-1",
  signal_id: "sig-1",
  state: { status: "open", severity: "warning", created_at: null, updated_at: null, last_seen_at: null, resolved_at: null, metadata: {}, resolved_condition_met: false },
  detector: { type: "expense", title: "Expense creep", description: "", domain: "expense", default_severity: "warning", recommended_actions: [], evidence_schema: [], scoring_profile: {} },
  evidence: [],
  related_audits: [],
  next_actions: [],
  clear_condition: { summary: "Spend must normalize.", type: "threshold", fields: ["current_total"], window_days: 14, comparator: "<=", target: 500 },
  playbooks: [],
  links: [],
});
const updateSignalStatus = vi.fn();
const getMonitorStatus = vi.fn();

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
vi.mock("../../api/dailyBrief", () => ({ publishDailyBrief: (...args: unknown[]) => publishDailyBrief(...args) }));
vi.mock("../../api/monitor", () => ({ getMonitorStatus: (...args: unknown[]) => getMonitorStatus(...args) }));

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

describe("AssistantPage daily brief", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    vi.clearAllMocks();
    fetchAssistantThread.mockResolvedValue([]);
  });

  it("renders daily brief and start playbook appends message without monitor calls", async () => {
    renderAssistant();
    await screen.findByText(/Daily brief for 2025-01-15/i);
    expect(screen.getByText(/Daily brief for 2025-01-15/i)).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Start Playbook: Inspect recent outflows/i }));

    await waitFor(() =>
      expect(postAssistantMessage).toHaveBeenCalledWith(
        "biz-1",
        expect.objectContaining({ kind: "playbook_started", signal_id: "sig-1" })
      )
    );
    expect(getMonitorStatus).not.toHaveBeenCalled();
  });
});
