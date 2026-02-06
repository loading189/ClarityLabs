import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import SignalsCenter from "./SignalsCenter";
import { AppStateProvider } from "../../app/state/appState";

const listSignalStates = vi.fn().mockResolvedValue({
  signals: [
    { id: "sig-1", type: "expense_creep", domain: "expense", severity: "red", status: "open", title: "Expense creep", summary: "Rising", updated_at: null },
    { id: "sig-2", type: "cash_runway", domain: "liquidity", severity: "yellow", status: "resolved", title: "Runway", summary: "Falling", updated_at: null },
  ],
  meta: {},
});
const getSignalDetail = vi.fn().mockImplementation((_biz: string, signalId: string) =>
  Promise.resolve({
    id: signalId,
    type: signalId === "sig-2" ? "cash_runway" : "expense_creep",
    domain: signalId === "sig-2" ? "liquidity" : "expense",
    severity: signalId === "sig-2" ? "yellow" : "red",
    status: "open",
    title: signalId === "sig-2" ? "Runway" : "Expense creep",
    summary: "Rising",
    payload_json: {},
    fingerprint: null,
    detected_at: null,
    last_seen_at: null,
    resolved_at: null,
    updated_at: null,
  })
);
const getSignalExplain = vi.fn().mockResolvedValue({ clear_condition: { summary: "ok", type: "threshold" } });
const fetchHealthScore = vi.fn().mockResolvedValue({ business_id: "biz-1", score: 50, generated_at: new Date().toISOString(), domains: [], contributors: [], meta: {} });
const getMonitorStatus = vi.fn().mockResolvedValue({
  business_id: "biz-1",
  last_pulse_at: null,
  newest_event_at: null,
  newest_event_source_event_id: null,
  open_count: 0,
  counts: { by_status: {}, by_severity: {} },
  gated: false,
  gating_reason: null,
  stale: true,
  stale_reason: "Monitoring has not run yet.",
});

vi.mock("../../api/signals", () => ({
  listSignalStates: (...args: unknown[]) => listSignalStates(...args),
  getSignalDetail: (...args: unknown[]) => getSignalDetail(...args),
  getSignalExplain: (...args: unknown[]) => getSignalExplain(...args),
  updateSignalStatus: vi.fn(),
  fetchSignals: vi.fn(),
}));
vi.mock("../../api/healthScore", () => ({ fetchHealthScore: (...args: unknown[]) => fetchHealthScore(...args) }));
vi.mock("../../api/audit", () => ({ getAuditLog: vi.fn().mockResolvedValue({ items: [], next_cursor: null }) }));
vi.mock("../../api/monitor", () => ({ getMonitorStatus: (...args: unknown[]) => getMonitorStatus(...args) }));

describe("SignalsCenter v2 filters", () => {
  it("renders status/severity/domain/search filters and applies", async () => {
    render(
      <AppStateProvider>
        <MemoryRouter>
          <SignalsCenter businessId="biz-1" />
        </MemoryRouter>
      </AppStateProvider>
    );

    await waitFor(() => expect(listSignalStates).toHaveBeenCalledWith("biz-1"));
    const user = userEvent.setup();

    await user.selectOptions(screen.getByLabelText("Status"), "resolved");
    expect(screen.queryByText("Expense creep")).not.toBeInTheDocument();
    expect(screen.getByText("Runway")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Status"), "open");
    await user.selectOptions(screen.getByLabelText("Domain"), "expense");
    expect(screen.queryByText("Runway")).not.toBeInTheDocument();

    const searchInput = screen.getByLabelText("Search");
    await user.clear(searchInput);
    await user.type(searchInput, "Expense");
    expect(searchInput).toHaveValue("Expense");
  });

  it("rehydrates the drawer from the signal_id query param", async () => {
    render(
      <AppStateProvider>
        <MemoryRouter initialEntries={["/signals?signal_id=sig-2"]}>
          <SignalsCenter businessId="biz-1" />
        </MemoryRouter>
      </AppStateProvider>
    );

    expect(await screen.findByText("Signal details")).toBeInTheDocument();
    expect(await screen.findByText("Runway")).toBeInTheDocument();
  });
});
