import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { AppStateProvider } from "../../app/state/appState";
import AssistantPage from "./AssistantPage";

const listSignalStates = vi.fn().mockResolvedValue({
  signals: [
    {
      id: "sig-1",
      type: "expense_creep_by_vendor",
      domain: "expense",
      severity: "high",
      status: "open",
      title: "Expense creep",
      summary: "Outflows increased",
      updated_at: new Date("2024-05-01T10:00:00Z").toISOString(),
    },
    {
      id: "sig-2",
      type: "low_cash_runway",
      domain: "liquidity",
      severity: "medium",
      status: "in_progress",
      title: "Low runway",
      summary: "Runway shrinking",
      updated_at: new Date("2024-05-02T10:00:00Z").toISOString(),
    },
    {
      id: "sig-3",
      type: "unusual_outflow_spike",
      domain: "expense",
      severity: "high",
      status: "resolved",
      title: "Outflow spike",
      summary: "One time spike",
      updated_at: new Date("2024-05-03T10:00:00Z").toISOString(),
    },
  ],
  meta: {},
});

const explainPayload = {
  business_id: "biz-1",
  signal_id: "sig-1",
  state: {
    status: "open",
    severity: "high",
    created_at: new Date("2024-05-01T09:00:00Z").toISOString(),
    updated_at: new Date("2024-05-01T10:00:00Z").toISOString(),
    last_seen_at: new Date("2024-05-01T10:00:00Z").toISOString(),
    resolved_at: null,
    metadata: {},
  },
  detector: {
    type: "expense_creep_by_vendor",
    title: "Expense creep by vendor",
    description: "Vendor outflows increased.",
    domain: "expense",
    default_severity: "warning",
    recommended_actions: ["Review spend"],
    evidence_schema: ["delta", "vendor_name"],
    scoring_profile: { weight: 1.1 },
  },
  evidence: [
    {
      key: "delta",
      label: "Delta",
      value: 300,
      source: "derived",
      anchors: { date_start: "2024-05-01", date_end: "2024-05-30", txn_ids: ["txn-1"] },
    },
    { key: "vendor_name", label: "Vendor", value: "Acme", source: "ledger" },
  ],
  related_audits: [
    {
      id: "audit-1",
      event_type: "signal_status_changed",
      actor: "Alex",
      reason: "triage",
      status: "open",
      created_at: new Date("2024-05-01T10:05:00Z").toISOString(),
    },
  ],
  links: ["/signals"],
};

const getSignalExplain = vi.fn().mockResolvedValue(explainPayload);

const updateSignalStatus = vi.fn().mockResolvedValue({
  business_id: "biz-1",
  signal_id: "sig-1",
  status: "resolved",
  last_seen_at: null,
  resolved_at: null,
  resolution_note: "handled",
  reason: "handled",
  audit_id: "audit-2",
});

const getMonitorStatus = vi.fn();
const fetchHealthScore = vi.fn().mockResolvedValue({
  business_id: "biz-1",
  score: 78,
  generated_at: new Date("2024-05-02T10:00:00Z").toISOString(),
  domains: [
    { domain: "liquidity", score: 70, penalty: 30, contributors: [] },
    { domain: "expense", score: 85, penalty: 15, contributors: [] },
  ],
  contributors: [
    {
      signal_id: "sig-1",
      domain: "expense",
      status: "open",
      severity: "warning",
      penalty: 12.5,
      rationale: "warning expense signal open",
    },
  ],
  meta: { model_version: "health_score_v1", weights: {} },
});
const fetchLedgerTransactions = vi.fn().mockResolvedValue([
  {
    occurred_at: new Date("2024-05-05T10:00:00Z").toISOString(),
    source_event_id: "txn-1",
    description: "Acme",
    direction: "outflow",
    signed_amount: -300,
    display_amount: 300,
    category_name: "General",
    account_name: "Expense",
  },
]);

vi.mock("../../api/signals", () => ({
  listSignalStates: (...args: unknown[]) => listSignalStates(...args),
  getSignalExplain: (...args: unknown[]) => getSignalExplain(...args),
  updateSignalStatus: (...args: unknown[]) => updateSignalStatus(...args),
}));

vi.mock("../../api/monitor", () => ({
  getMonitorStatus: (...args: unknown[]) => getMonitorStatus(...args),
}));

vi.mock("../../api/healthScore", () => ({
  fetchHealthScore: (...args: unknown[]) => fetchHealthScore(...args),
}));

vi.mock("../../api/ledger", () => ({
  fetchLedgerTransactions: (...args: unknown[]) => fetchLedgerTransactions(...args),
}));

function renderAssistant(path = "/assistant?businessId=biz-1") {
  return render(
    <AppStateProvider>
      <MemoryRouter initialEntries={[path]}>
        <AssistantPage />
      </MemoryRouter>
    </AppStateProvider>
  );
}

describe("AssistantPage", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("loads signals and does not call monitor status", async () => {
    renderAssistant();

    await waitFor(() => expect(listSignalStates).toHaveBeenCalledWith("biz-1"));
    await waitFor(() => expect(fetchHealthScore).toHaveBeenCalledWith("biz-1"));
    expect(getMonitorStatus).not.toHaveBeenCalled();
    expect(screen.getByText(/Tracking 2 active alerts/i)).toBeInTheDocument();
    expect(screen.getByText("Health score")).toBeInTheDocument();
  });

  it("loads explain data from query params and renders evidence", async () => {
    renderAssistant("/assistant?businessId=biz-1&signalId=sig-1");

    await waitFor(() => expect(getSignalExplain).toHaveBeenCalledWith("biz-1", "sig-1"));
    expect(screen.getByText("Vendor")).toBeInTheDocument();
    expect(screen.getByText("Acme")).toBeInTheDocument();
  });

  it("opens breakdown and selects a contributor", async () => {
    renderAssistant();

    await waitFor(() => expect(fetchHealthScore).toHaveBeenCalled());

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /View breakdown/i }));
    await user.click(screen.getByRole("button", { name: /Expense creep/i }));

    await waitFor(() => expect(getSignalExplain).toHaveBeenCalledWith("biz-1", "sig-1"));
  });

  it("loads ledger trace transactions from evidence anchors", async () => {
    renderAssistant("/assistant?businessId=biz-1&signalId=sig-1");

    await waitFor(() => expect(getSignalExplain).toHaveBeenCalledWith("biz-1", "sig-1"));

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /View transactions/i }));

    await waitFor(() =>
      expect(fetchLedgerTransactions).toHaveBeenCalledWith("biz-1", { txn_ids: ["txn-1"] })
    );
    expect(screen.getByText("Acme")).toBeInTheDocument();
  });

  it("updates status from action chips and refreshes explain", async () => {
    getSignalExplain
      .mockResolvedValueOnce(explainPayload)
      .mockResolvedValueOnce({
        ...explainPayload,
        state: { ...explainPayload.state, status: "resolved" },
      });

    renderAssistant("/assistant?businessId=biz-1&signalId=sig-1");

    await waitFor(() => expect(getSignalExplain).toHaveBeenCalled());

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Resolve/i }));

    await user.type(screen.getByLabelText("Actor"), "Jordan");
    await user.type(screen.getByLabelText("Reason"), "Handled in workflow");

    await user.click(screen.getByRole("button", { name: /Confirm update/i }));

    await waitFor(() =>
      expect(updateSignalStatus).toHaveBeenCalledWith("biz-1", "sig-1", {
        status: "resolved",
        actor: "Jordan",
        reason: "Handled in workflow",
      })
    );
    expect(getSignalExplain.mock.calls.length).toBeGreaterThan(1);
  });
});
