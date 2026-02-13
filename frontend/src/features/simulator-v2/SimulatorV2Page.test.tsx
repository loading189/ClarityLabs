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

vi.mock("../../api/simV2", () => ({
  getSimV2Catalog: (...a: unknown[]) => getSimV2Catalog(...a),
  seedSimV2: (...a: unknown[]) => seedSimV2(...a),
  resetSimV2: (...a: unknown[]) => resetSimV2(...a),
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
});
