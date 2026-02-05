import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import SignalsCenter from "./SignalsCenter";

const listSignalStates = vi.fn().mockResolvedValue({
  signals: [
    {
      id: "sig-1",
      type: "expense_creep",
      severity: "red",
      status: "open",
      title: "Expense creep detected",
      summary: "Outflow is rising",
      updated_at: new Date("2024-05-01T10:00:00Z").toISOString(),
    },
    {
      id: "sig-2",
      type: "cash_runway_trend",
      severity: "yellow",
      status: "resolved",
      title: "Runway declining",
      summary: "Cash runway shortening",
      updated_at: new Date("2024-05-02T12:00:00Z").toISOString(),
    },
  ],
  meta: {},
});

const getSignalDetail = vi.fn().mockResolvedValue({
  id: "sig-1",
  type: "expense_creep",
  severity: "red",
  status: "open",
  title: "Expense creep detected",
  summary: "Outflow is rising",
  payload_json: { vendor: "Acme", total: 1200 },
  fingerprint: "fp",
  detected_at: new Date("2024-05-01T09:00:00Z").toISOString(),
  last_seen_at: new Date("2024-05-01T10:00:00Z").toISOString(),
  resolved_at: null,
  updated_at: new Date("2024-05-01T10:00:00Z").toISOString(),
});

const getSignalExplain = vi.fn().mockResolvedValue({ clear_condition: { summary: "Spend returns to baseline", type: "threshold" } });
const updateSignalStatus = vi.fn();
const getAuditLog = vi.fn().mockResolvedValue({ items: [], next_cursor: null });
const fetchSignals = vi.fn();
const fetchHealthScore = vi.fn().mockResolvedValue({
  business_id: "biz-1",
  score: 82,
  generated_at: new Date("2024-05-02T10:00:00Z").toISOString(),
  domains: [
    { domain: "liquidity", score: 74, penalty: 26, contributors: [] },
    { domain: "expense", score: 88, penalty: 12, contributors: [] },
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

vi.mock("../../api/signals", () => ({
  listSignalStates: (...args: unknown[]) => listSignalStates(...args),
  getSignalDetail: (...args: unknown[]) => getSignalDetail(...args),
  getSignalExplain: (...args: unknown[]) => getSignalExplain(...args),
  updateSignalStatus: (...args: unknown[]) => updateSignalStatus(...args),
  fetchSignals: (...args: unknown[]) => fetchSignals(...args),
}));

vi.mock("../../api/audit", () => ({
  getAuditLog: (...args: unknown[]) => getAuditLog(...args),
}));

vi.mock("../../api/healthScore", () => ({
  fetchHealthScore: (...args: unknown[]) => fetchHealthScore(...args),
}));

describe("SignalsCenter", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders signals and filters by status", async () => {
    render(
      <MemoryRouter>
        <SignalsCenter businessId="biz-1" />
      </MemoryRouter>
    );

    await waitFor(() => expect(listSignalStates).toHaveBeenCalled());
    await waitFor(() => expect(fetchHealthScore).toHaveBeenCalledWith("biz-1"));
    expect(screen.getByText("Expense creep detected")).toBeInTheDocument();
    expect(screen.getByText("Runway declining")).toBeInTheDocument();

    const user = userEvent.setup();
    const statusSelect = screen.getByLabelText("Status");
    await user.selectOptions(statusSelect, "resolved");

    expect(screen.queryByText("Expense creep detected")).not.toBeInTheDocument();
    expect(screen.getByText("Runway declining")).toBeInTheDocument();
  });

  it("opens the detail drawer and renders payload JSON", async () => {
    render(
      <MemoryRouter>
        <SignalsCenter businessId="biz-1" />
      </MemoryRouter>
    );

    await waitFor(() => expect(listSignalStates).toHaveBeenCalled());

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Expense creep detected/i }));

    await waitFor(() => expect(getSignalDetail).toHaveBeenCalledWith("biz-1", "sig-1"));
    expect(screen.getByText(/"vendor": "Acme"/i)).toBeInTheDocument();
    expect(screen.getByText(/"total": 1200/i)).toBeInTheDocument();
  });

  it("renders health score widget and opens breakdown", async () => {
    render(
      <MemoryRouter>
        <SignalsCenter businessId="biz-1" />
      </MemoryRouter>
    );

    await waitFor(() => expect(fetchHealthScore).toHaveBeenCalled());
    expect(screen.getByText(/Health score/i)).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /View breakdown/i }));

    expect(screen.getByText(/Contributors/i)).toBeInTheDocument();
  });

  it("provides a send to assistant deep link", async () => {
    render(
      <MemoryRouter>
        <SignalsCenter businessId="biz-1" />
      </MemoryRouter>
    );

    await waitFor(() => expect(listSignalStates).toHaveBeenCalled());

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Expense creep detected/i }));

    const assistantLink = await screen.findByRole("link", { name: /Open in Assistant/i });
    expect(assistantLink).toHaveAttribute(
      "href",
      "/app/biz-1/assistant?signalId=sig-1"
    );
  });
});
