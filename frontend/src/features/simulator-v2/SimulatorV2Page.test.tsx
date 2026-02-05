import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AppStateProvider } from "../../app/state/appState";
import SimulatorV2Page from "./SimulatorV2Page";

const getSimV2Catalog = vi.fn().mockResolvedValue({
  presets: [{ id: "healthy", title: "Healthy", scenarios: [{ id: "steady_state", intensity: 1 }] }],
  scenarios: [{ id: "cash_crunch", title: "Cash Crunch", description: "", expected_signals: [] }],
});
const seedSimV2 = vi.fn().mockResolvedValue({
  window: { start_date: "2025-01-01", end_date: "2025-02-01" },
  stats: { raw_events_inserted: 12, pulse_ran: true },
  signals: { total: 3 },
  coverage: {
    window_observed: { start_date: "2025-01-01", end_date: "2025-02-01" },
    inputs: {
      raw_events_count: 20,
      normalized_txns_count: 18,
      deposits_count_last30: 8,
      expenses_count_last30: 12,
      distinct_vendors_last30: 4,
      balance_series_points: 18,
    },
    detectors: [
      {
        detector_id: "detect_liquidity_runway_low",
        signal_id: "liquidity.runway_low",
        domain: "liquidity",
        ran: true,
        fired: true,
        severity: "warning",
        evidence_keys: ["runway_days"],
      },
    ],
  },
});
const resetSimV2 = vi.fn().mockResolvedValue({});

vi.mock("../../api/simV2", () => ({
  getSimV2Catalog: (...a: unknown[]) => getSimV2Catalog(...a),
  seedSimV2: (...a: unknown[]) => seedSimV2(...a),
  resetSimV2: (...a: unknown[]) => resetSimV2(...a),
}));

describe("SimulatorV2Page", () => {
  it("loads catalog and seeds preset", async () => {
    render(
      <AppStateProvider>
        <MemoryRouter initialEntries={["/app/b1/admin/simulator"]}>
          <Routes>
            <Route path="/app/:businessId/admin/simulator" element={<SimulatorV2Page />} />
          </Routes>
        </MemoryRouter>
      </AppStateProvider>
    );

    await waitFor(() => expect(getSimV2Catalog).toHaveBeenCalled());
    fireEvent.click(await screen.findByText("Seed Healthy"));
    await waitFor(() => expect(seedSimV2).toHaveBeenCalled());
    expect(await screen.findByText(/Signals produced: 3/)).toBeInTheDocument();
    expect(await screen.findByText(/Coverage Report/)).toBeInTheDocument();
    expect(await screen.findByText(/detect_liquidity_runway_low/)).toBeInTheDocument();
  });
});
