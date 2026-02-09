import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import LedgerPage from "./LedgerPage";
import styles from "./LedgerPage.module.css";
import { AppStateProvider } from "../../app/state/appState";

const fetchLedgerQuery = vi.fn();
const fetchLedgerAccountDimensions = vi.fn();
const fetchLedgerVendorDimensions = vi.fn();
const fetchTransactionDetail = vi.fn();

vi.mock("../../api/ledger", () => ({
  fetchLedgerQuery: (...args: unknown[]) => fetchLedgerQuery(...args),
  fetchLedgerAccountDimensions: (...args: unknown[]) => fetchLedgerAccountDimensions(...args),
  fetchLedgerVendorDimensions: (...args: unknown[]) => fetchLedgerVendorDimensions(...args),
}));
vi.mock("../../api/transactions", () => ({
  fetchTransactionDetail: (...args: unknown[]) => fetchTransactionDetail(...args),
}));
vi.mock("../../app/auth/AuthContext", () => ({
  useAuth: () => ({ logout: vi.fn() }),
}));

const BIZ_ID = "11111111-1111-4111-8111-111111111111";

function renderPage(path = `/app/${BIZ_ID}/ledger?anchor_source_event_id=evt-2`) {
  return render(
    <AppStateProvider>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route
            path="/app/:businessId/ledger"
            element={
              <>
                <LedgerPage />
                <LocationDisplay />
              </>
            }
          />
        </Routes>
      </MemoryRouter>
    </AppStateProvider>
  );
}

function LocationDisplay() {
  const location = useLocation();
  return <div data-testid="location">{location.search}</div>;
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
    fetchTransactionDetail.mockResolvedValue({
      business_id: BIZ_ID,
      source_event_id: "evt-2",
      raw_event: { source: "bank", source_event_id: "evt-2", payload: {}, occurred_at: "2024-01-02", created_at: "2024-01-02", processed_at: null },
      normalized_txn: { source_event_id: "evt-2", occurred_at: "2024-01-02", date: "2024-01-02", description: "Rent", amount: -20, direction: "outflow", account: "Operating", category_hint: "Rent" },
      vendor_normalization: { canonical_name: "Landlord", source: "manual" },
      categorization: null,
      processing_assumptions: [],
      ledger_context: null,
      audit_history: [],
      related_signals: [],
    });

    renderPage();
    const rentCells = await screen.findAllByText("Rent");
    const rentRow = rentCells[0]?.closest("tr");
    expect(rentRow).not.toBeNull();
    await waitFor(() => expect(rentRow).toHaveClass(styles.rowSelected));
  });

  it("updates anchor query param when clicking a row", async () => {
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
      ],
      summary: { row_count: 1, start_balance: 0, end_balance: 0, total_in: 0, total_out: 0 },
    });
    fetchLedgerAccountDimensions.mockResolvedValue([]);
    fetchLedgerVendorDimensions.mockResolvedValue([]);
    fetchTransactionDetail.mockResolvedValue({
      business_id: BIZ_ID,
      source_event_id: "evt-1",
      raw_event: { source: "bank", source_event_id: "evt-1", payload: {}, occurred_at: "2024-01-01", created_at: "2024-01-01", processed_at: null },
      normalized_txn: { source_event_id: "evt-1", occurred_at: "2024-01-01", date: "2024-01-01", description: "Coffee", amount: -12, direction: "outflow", account: "Operating", category_hint: "Meals" },
      vendor_normalization: { canonical_name: "Cafe", source: "manual" },
      categorization: null,
      processing_assumptions: [],
      ledger_context: null,
      audit_history: [],
      related_signals: [],
    });

    renderPage(`/app/${BIZ_ID}/ledger`);
    const user = userEvent.setup();
    const row = await screen.findByText("Coffee");
    await user.click(row);

    const location = screen.getByTestId("location");
    await waitFor(() => expect(location.textContent).toContain("anchor_source_event_id=evt-1"));
  });

  it("rehydrates the transaction drawer from the anchor param", async () => {
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
      ],
      summary: { row_count: 1, start_balance: 0, end_balance: 0, total_in: 0, total_out: 0 },
    });
    fetchLedgerAccountDimensions.mockResolvedValue([]);
    fetchLedgerVendorDimensions.mockResolvedValue([]);
    fetchTransactionDetail.mockResolvedValue({
      business_id: BIZ_ID,
      source_event_id: "evt-1",
      raw_event: { source: "bank", source_event_id: "evt-1", payload: {}, occurred_at: "2024-01-01", created_at: "2024-01-01", processed_at: null },
      normalized_txn: { source_event_id: "evt-1", occurred_at: "2024-01-01", date: "2024-01-01", description: "Coffee", amount: -12, direction: "outflow", account: "Operating", category_hint: "Meals" },
      vendor_normalization: { canonical_name: "Cafe", source: "manual" },
      categorization: null,
      processing_assumptions: [],
      ledger_context: null,
      audit_history: [],
      related_signals: [],
    });

    renderPage(`/app/${BIZ_ID}/ledger?anchor_source_event_id=evt-1`);
    expect(await screen.findByText("Transaction detail")).toBeInTheDocument();
  });
});
