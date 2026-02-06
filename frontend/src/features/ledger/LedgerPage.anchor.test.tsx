import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import LedgerPage from "./LedgerPage";
import styles from "./LedgerPage.module.css";
import { AppStateProvider } from "../../app/state/appState";

const fetchLedgerQuery = vi.fn();
const fetchLedgerAccountDimensions = vi.fn();
const fetchLedgerVendorDimensions = vi.fn();

vi.mock("../../api/ledger", () => ({
  fetchLedgerQuery: (...args: unknown[]) => fetchLedgerQuery(...args),
  fetchLedgerAccountDimensions: (...args: unknown[]) => fetchLedgerAccountDimensions(...args),
  fetchLedgerVendorDimensions: (...args: unknown[]) => fetchLedgerVendorDimensions(...args),
}));

const BIZ_ID = "11111111-1111-4111-8111-111111111111";

function renderPage(path = `/app/${BIZ_ID}/ledger?anchor_source_event_id=evt-2`) {
  return render(
    <AppStateProvider>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/app/:businessId/ledger" element={<LedgerPage />} />
        </Routes>
      </MemoryRouter>
    </AppStateProvider>
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  localStorage.clear();
});

describe("LedgerPage anchor behavior", () => {
  it("highlights anchored row from query param", async () => {
    fetchLedgerQuery.mockResolvedValue({
      rows: [
        {
          occurred_at: "2024-01-01",
          date: "2024-01-01",
          description: "Coffee",
          vendor: "Cafe",
          amount: -12,
          category: "Meals",
          account: "Operating",
          balance: 100,
          source_event_id: "evt-1",
        },
        {
          occurred_at: "2024-01-02",
          date: "2024-01-02",
          description: "Rent",
          vendor: "Landlord",
          amount: -20,
          category: "Rent",
          account: "Operating",
          balance: 80,
          source_event_id: "evt-2",
        },
      ],
      summary: { row_count: 2, start_balance: 0, end_balance: 0, total_in: 0, total_out: 0 },
    });
    fetchLedgerAccountDimensions.mockResolvedValue([]);
    fetchLedgerVendorDimensions.mockResolvedValue([]);

    renderPage();
    const rentCells = await screen.findAllByText("Rent");
    const rentRow = rentCells[0]?.closest("tr");
    expect(rentRow).not.toBeNull();
    await waitFor(() => expect(rentRow).toHaveClass(styles.rowSelected));
  });
});
