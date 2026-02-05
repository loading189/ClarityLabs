import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AppStateProvider } from "../../app/state/appState";
import AssistantPage from "./AssistantPage";

const listSignalStates = vi.fn().mockResolvedValue({
  signals: [
    { id: "sig-1", type: "expense", domain: "expense", severity: "warning", status: "open", title: "Expense creep", summary: null, updated_at: null },
  ],
  meta: {},
});
const fetchHealthScore = vi.fn().mockResolvedValue({ business_id: "biz-1", score: 78, generated_at: new Date().toISOString(), domains: [], contributors: [{ signal_id: "sig-1", domain: "expense", status: "open", severity: "warning", penalty: 12, rationale: "" }], meta: { model_version: "v1", weights: {} } });
const fetchHealthScoreExplainChange = vi.fn().mockResolvedValue({
  business_id: "biz-1",
  computed_at: new Date().toISOString(),
  window: { since_hours: 72 },
  changes: [],
  impacts: [{ signal_id: "sig-1", domain: "expense", severity: "warning", change_type: "signal_detected", estimated_penalty_delta: -12, rationale: "Detected" }],
  summary: { headline: "Health score likely declined by 12 points from recent changes.", net_estimated_delta: -12, top_drivers: ["sig-1"] },
});
const listChanges = vi.fn().mockResolvedValue([
  { id: "chg-1", occurred_at: new Date().toISOString(), type: "signal_detected", business_id: "biz-1", signal_id: "sig-1", severity: "warning", domain: "expense", title: "Expense creep", actor: "system", reason: "detected", summary: "Detected", links: { assistant: "", signals: "" } },
]);
const fetchAssistantThread = vi.fn().mockResolvedValue([]);
const postAssistantMessage = vi.fn().mockResolvedValue({
  id: "msg-1",
  business_id: "biz-1",
  created_at: new Date().toISOString(),
  author: "assistant",
  kind: "summary",
  signal_id: null,
  audit_id: null,
  content_json: { text: "ok" },
});
const getSignalExplain = vi.fn().mockResolvedValue({
  business_id: "biz-1",
  signal_id: "sig-1",
  state: { status: "open", severity: "warning", created_at: null, updated_at: null, last_seen_at: null, resolved_at: null, metadata: {} },
  detector: { type: "expense", title: "Expense creep", description: "", domain: "expense", default_severity: "warning", recommended_actions: [], evidence_schema: [], scoring_profile: {} },
  evidence: [],
  related_audits: [],
  next_actions: [{ key: "resolve_if_fixed", label: "Resolve", action: "resolve", requires_reason: true, rationale: "", suggested_snooze_minutes: null, guardrails: [] }],
  links: [],
});
const updateSignalStatus = vi.fn().mockResolvedValue({ business_id: "biz-1", signal_id: "sig-1", status: "resolved", last_seen_at: null, resolved_at: null, resolution_note: "done", reason: "done", audit_id: "audit-1" });
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
vi.mock("../../api/monitor", () => ({ getMonitorStatus: (...args: unknown[]) => getMonitorStatus(...args) }));

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

describe("AssistantPage v2", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    vi.clearAllMocks();
    fetchAssistantThread.mockResolvedValue([]);
  });

  it("loads server-backed thread on mount", async () => {
    renderAssistant();
    await waitFor(() => expect(fetchAssistantThread).toHaveBeenCalledWith("biz-1", 200));
    expect(getMonitorStatus).not.toHaveBeenCalled();
  });

  it("if thread empty, seeds messages via POST", async () => {
    renderAssistant();
    await waitFor(() => expect(postAssistantMessage).toHaveBeenCalled());
    expect(postAssistantMessage.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it("clicking a priority appends explain message and loads explain", async () => {
    renderAssistant();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /1\. Expense creep/i }));
    await waitFor(() => expect(getSignalExplain).toHaveBeenCalledWith("biz-1", "sig-1"));
    expect(postAssistantMessage).toHaveBeenCalledWith(
      "biz-1",
      expect.objectContaining({ kind: "explain", signal_id: "sig-1" })
    );
  });

  it("performing next_action posts action_result with audit_id", async () => {
    renderAssistant();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /1\. Expense creep/i }));
    await screen.findByRole("button", { name: /Resolve/i });
    await user.clear(screen.getByLabelText("Reason"));
    await user.type(screen.getByLabelText("Reason"), "Handled");
    await user.click(screen.getByRole("button", { name: /Resolve/i }));
    await waitFor(() => expect(updateSignalStatus).toHaveBeenCalled());
    expect(postAssistantMessage).toHaveBeenCalledWith(
      "biz-1",
      expect.objectContaining({ kind: "action_result", audit_id: "audit-1" })
    );
  });

  it("renders score change explanation and appends summary message on click", async () => {
    renderAssistant();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /health score likely declined/i }));
    await waitFor(() =>
      expect(postAssistantMessage).toHaveBeenCalledWith(
        "biz-1",
        expect.objectContaining({ kind: "changes" })
      )
    );
  });
});
