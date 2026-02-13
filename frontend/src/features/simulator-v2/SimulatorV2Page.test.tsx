import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AppStateProvider } from "../../app/state/appState";
import SimulatorV2Page from "./SimulatorV2Page";

const getSimV2Catalog = vi.fn().mockResolvedValue({
  scenarios: [{ id: "baseline_stable", name: "Baseline Stable", description: "", tags: ["baseline"], parameters: {} }],
});
const seedSimV2 = vi.fn().mockResolvedValue({
  scenario_id: "baseline_stable",
  seed_key: 123,
  summary: {
    txns_created: 12,
    ledger_rows: 11,
    signals_open_count: 3,
    actions_open_count: 2,
  },
});
const resetSimV2 = vi.fn().mockResolvedValue({});
const ensureDynamicPlaidItem = vi.fn().mockResolvedValue({ status: "ready" });
const pumpPlaidTransactions = vi.fn().mockResolvedValue({
  business_id: "b1",
  date_range: { start_date: "2026-01-01", end_date: "2026-01-31" },
  seed_key: "seed",
  txns_requested: 120,
  txns_created: 119,
  sync: { new: 40, updated: 0, removed: 0, cursor: "c1" },
  pipeline: { ledger_rows: 100, signals_open_count: 4 },
  actions: { created_count: 3, updated_count: 1, suppressed_count: 2, suppression_reasons: { duplicate: 2 } },
});

vi.mock("../../api/simV2", () => ({
  getSimV2Catalog: (...a: unknown[]) => getSimV2Catalog(...a),
  seedSimV2: (...a: unknown[]) => seedSimV2(...a),
  resetSimV2: (...a: unknown[]) => resetSimV2(...a),
}));

vi.mock("../../api/plaid", () => ({
  ensureDynamicPlaidItem: (...a: unknown[]) => ensureDynamicPlaidItem(...a),
  pumpPlaidTransactions: (...a: unknown[]) => pumpPlaidTransactions(...a),
}));

describe("SimulatorV2Page", () => {
  it("loads catalog and seeds scenario", async () => {
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
    fireEvent.click(await screen.findByText("Seed"));
    await waitFor(() => expect(seedSimV2).toHaveBeenCalled());
    expect(await screen.findByText(/Open signals: 3/)).toBeInTheDocument();
    expect(await screen.findByText(/Transactions created: 12/)).toBeInTheDocument();
  });

  it("calls plaid pump endpoints and renders telemetry", async () => {
    render(
      <AppStateProvider>
        <MemoryRouter initialEntries={["/app/b1/admin/simulator"]}>
          <Routes>
            <Route path="/app/:businessId/admin/simulator" element={<SimulatorV2Page />} />
          </Routes>
        </MemoryRouter>
      </AppStateProvider>
    );

    fireEvent.click((await screen.findAllByText("Ensure Dynamic Item"))[0]);
    await waitFor(() => expect(ensureDynamicPlaidItem).toHaveBeenCalledWith("b1", false));

    fireEvent.click(screen.getAllByText("Pump Transactions")[0]);
    await waitFor(() => expect(pumpPlaidTransactions).toHaveBeenCalled());
    expect(await screen.findByText(/"txns_created": 119/)).toBeInTheDocument();
  });
});
