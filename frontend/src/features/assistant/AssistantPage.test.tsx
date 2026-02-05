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
const listChanges = vi.fn().mockResolvedValue([
  { id: "chg-1", occurred_at: new Date().toISOString(), type: "signal_detected", business_id: "biz-1", signal_id: "sig-1", severity: "warning", domain: "expense", title: "Expense creep", actor: "system", reason: "detected", summary: "Detected", links: { assistant: "", signals: "" } },
]);
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
vi.mock("../../api/healthScore", () => ({ fetchHealthScore: (...args: unknown[]) => fetchHealthScore(...args) }));
vi.mock("../../api/changes", () => ({ listChanges: (...args: unknown[]) => listChanges(...args) }));
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

describe("AssistantPage v1", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it("renders health score, top priorities and recent changes", async () => {
    renderAssistant();
    await waitFor(() => expect(fetchHealthScore).toHaveBeenCalledWith("biz-1"));
    expect(await screen.findByText("Top priorities")).toBeInTheDocument();
    expect(await screen.findByText("Recent changes")).toBeInTheDocument();
    expect(getMonitorStatus).not.toHaveBeenCalled();
  });

  it("clicking a change loads explain and renders next actions", async () => {
    renderAssistant();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /signal detected/i }));
    await waitFor(() => expect(getSignalExplain).toHaveBeenCalledWith("biz-1", "sig-1"));
    expect(await screen.findByRole("button", { name: /Resolve/i })).toBeInTheDocument();
  });

  it("clicking next action updates status and refreshes", async () => {
    renderAssistant();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /signal detected/i }));
    await screen.findByRole("button", { name: /Resolve/i });
    await user.clear(screen.getByLabelText("Reason"));
    await user.type(screen.getByLabelText("Reason"), "Handled");
    await user.click(screen.getByRole("button", { name: /Resolve/i }));
    await waitFor(() => expect(updateSignalStatus).toHaveBeenCalled());
    expect(listSignalStates.mock.calls.length).toBeGreaterThan(1);
    expect(fetchHealthScore.mock.calls.length).toBeGreaterThan(1);
    expect(getSignalExplain.mock.calls.length).toBeGreaterThan(1);
  });

  it("loads persisted thread from localStorage", async () => {
    localStorage.setItem(
      "clarity.assistant.thread.biz-1",
      JSON.stringify([{ id: "a", type: "system", created_at: new Date().toISOString(), payload: { text: "persisted" } }])
    );
    renderAssistant();
    expect(await screen.findByText("persisted")).toBeInTheDocument();
  });
});
