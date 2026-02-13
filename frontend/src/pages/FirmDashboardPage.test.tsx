import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import FirmDashboardPage from "./FirmDashboardPage";

const fetchFirmOverview = vi.fn();

vi.mock("../api/firm", () => ({
  fetchFirmOverview: (...args: unknown[]) => fetchFirmOverview(...args),
}));

vi.mock("../api/dataStatus", () => ({
  fetchDataStatus: vi.fn().mockResolvedValue({
    latest_event: { source: "plaid", occurred_at: new Date().toISOString() },
    open_signals: 0,
    open_actions: 0,
    ledger_rows: 0,
    uncategorized_txns: 0,
    last_sync_at: new Date().toISOString(),
  }),
}));

describe("FirmDashboardPage", () => {
  it("renders businesses, applies risk band style, keeps rows sorted, and CTA navigation works", async () => {
    fetchFirmOverview.mockResolvedValue({
      generated_at: "2024-01-01T00:00:00Z",
      businesses: [
        {
          business_id: "biz-1",
          business_name: "Alpha",
          risk_score: 25,
          risk_band: "watch",
          open_signals: 2,
          signals_by_severity: { critical: 0, warning: 1, info: 1 },
          open_actions: 1,
          stale_actions: 0,
          uncategorized_txn_count: 1,
          latest_signal_at: "2024-01-01T00:00:00Z",
          latest_action_at: null,
        },
        {
          business_id: "biz-2",
          business_name: "Zulu",
          risk_score: 80,
          risk_band: "at_risk",
          open_signals: 4,
          signals_by_severity: { critical: 2, warning: 1, info: 1 },
          open_actions: 3,
          stale_actions: 2,
          uncategorized_txn_count: 2,
          latest_signal_at: "2024-01-02T00:00:00Z",
          latest_action_at: "2024-01-03T00:00:00Z",
        },
      ],
    });

    render(
      <MemoryRouter initialEntries={["/app/dashboard"]}>
        <Routes>
          <Route path="/app/dashboard" element={<FirmDashboardPage />} />
          <Route path="/app/:businessId/advisor" element={<div>Inbox Route</div>} />
          <Route path="/app/:businessId/signals" element={<div>Signals Route</div>} />
        </Routes>
      </MemoryRouter>
    );

    expect(await screen.findByText("Firm Risk Dashboard")).toBeInTheDocument();
    expect(screen.getAllByText("Alpha").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Zulu").length).toBeGreaterThan(0);

    const rows = screen.getAllByRole("row");
    const firstDataRow = rows[1];
    expect(within(firstDataRow).getByText("Zulu")).toBeInTheDocument();

    const zuluBand = screen.getByTestId("risk-band-biz-2");
    expect(zuluBand).toHaveAttribute("data-band", "at_risk");

    await userEvent.click(within(firstDataRow).getByRole("button", { name: "View Inbox" }));
    await waitFor(() => expect(screen.getByText("Inbox Route")).toBeInTheDocument());
  });
});
