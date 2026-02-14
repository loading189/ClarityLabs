import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import LedgerPage from "./LedgerPage";
import { AppStateProvider } from "../../app/state/appState";

const fetchLedgerQuery = vi.fn();
const fetchLedgerAccountDimensions = vi.fn();
const fetchLedgerVendorDimensions = vi.fn();

vi.mock("../../api/dataStatus", () => ({
  fetchDataStatus: vi.fn().mockResolvedValue({
    latest_event: { source: "plaid", occurred_at: new Date().toISOString() },
    open_signals: 1,
    open_actions: 1,
    ledger_rows: 10,
    uncategorized_txns: 1,
    last_sync_at: new Date().toISOString(),
  }),
}));

vi.mock("../../api/ledger", () => ({
  fetchLedgerQuery: (...args: unknown[]) => fetchLedgerQuery(...args),
  fetchLedgerAccountDimensions: (...args: unknown[]) => fetchLedgerAccountDimensions(...args),
  fetchLedgerVendorDimensions: (...args: unknown[]) => fetchLedgerVendorDimensions(...args),
}));
vi.mock("../../app/auth/AuthContext", () => ({
  useAuth: () => ({ logout: vi.fn() }),
}));

const BIZ_ID = "11111111-1111-4111-8111-111111111111";

function renderPage(path = `/app/${BIZ_ID}/ledger`) {
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

describe("LedgerPage sidebar", () => {
  it("loads accounts/vendors dimensions", async () => {
    fetchLedgerQuery.mockResolvedValue({ rows: [], summary: { row_count: 0, start_balance: 0, end_balance: 0, total_in: 0, total_out: 0 }, total_count: 0, has_more: false, next_offset: null });
    fetchLedgerAccountDimensions.mockResolvedValue([{ account: "Operating", label: "Operating", count: 2, total: 100 }]);
    fetchLedgerVendorDimensions.mockResolvedValue([{ vendor: "Acme", count: 2, total: -50 }]);

    renderPage();
    await waitFor(() => expect(fetchLedgerAccountDimensions).toHaveBeenCalled());
    expect(await screen.findByText(/Operating/)).toBeInTheDocument();
  });

  it("clicking account filters ledger API call", async () => {
    fetchLedgerQuery.mockResolvedValue({ rows: [], summary: { row_count: 0, start_balance: 0, end_balance: 0, total_in: 0, total_out: 0 }, total_count: 0, has_more: false, next_offset: null });
    fetchLedgerAccountDimensions.mockResolvedValue([{ account: "Operating", label: "Operating", count: 2, total: 100 }]);
    fetchLedgerVendorDimensions.mockResolvedValue([]);

    renderPage();
    await screen.findByText("Operating");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Operating/ }));

    await waitFor(() => {
      const calls = fetchLedgerQuery.mock.calls;
      expect(calls[calls.length - 1][1].account).toEqual(["Operating"]);
    });
  });

  it("query params restore state", async () => {
    fetchLedgerQuery.mockResolvedValue({ rows: [], summary: { row_count: 0, start_balance: 0, end_balance: 0, total_in: 0, total_out: 0 }, total_count: 0, has_more: false, next_offset: null });
    fetchLedgerAccountDimensions.mockResolvedValue([]);
    fetchLedgerVendorDimensions.mockResolvedValue([]);

    renderPage(`/app/${BIZ_ID}/ledger?account=Operating&vendor=Acme%20Inc&q=rent&category=uncategorized`);

    await waitFor(() => expect(fetchLedgerQuery).toHaveBeenCalled());
    const call = fetchLedgerQuery.mock.calls[0][1];
    expect(call.account).toEqual(["Operating"]);
    expect(call.vendor).toEqual(["Acme Inc"]);
    expect(call.search).toBe("rent");
    expect(screen.getByRole("button", { name: /Uncategorized ✕/i })).toBeInTheDocument();
  });

  it("filters sidebar list with in-panel search", async () => {
    fetchLedgerQuery.mockResolvedValue({ rows: [], summary: { row_count: 0, start_balance: 0, end_balance: 0, total_in: 0, total_out: 0 }, total_count: 0, has_more: false, next_offset: null });
    fetchLedgerAccountDimensions.mockResolvedValue([
      { account: "Operating", label: "Operating", count: 2, total: 100 },
      { account: "Payroll", label: "Payroll", count: 1, total: 50 },
    ]);
    fetchLedgerVendorDimensions.mockResolvedValue([]);

    renderPage();
    const user = userEvent.setup();
    await screen.findByText("Operating");
    await user.type(screen.getByRole("textbox", { name: /Sidebar search/i }), "pay");

    expect(screen.getByRole("button", { name: /Payroll/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Operating/ })).not.toBeInTheDocument();
  });

  it("uncategorized toggle filters visible rows", async () => {
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
          description: "Unknown",
          vendor: "",
          amount: -20,
          category: "",
          account: "Operating",
          balance: 80,
          source_event_id: "evt-2",
        },
      ],
      summary: { row_count: 2, start_balance: 0, end_balance: 0, total_in: 0, total_out: 0 },
      total_count: 2,
      has_more: false,
      next_offset: null,
    });
    fetchLedgerAccountDimensions.mockResolvedValue([]);
    fetchLedgerVendorDimensions.mockResolvedValue([]);

    renderPage();
    const user = userEvent.setup();
    await screen.findByText("Coffee");
    await user.click(screen.getByRole("button", { name: /Uncategorized only/i }));

    expect(screen.queryByText("Coffee")).not.toBeInTheDocument();
    expect(screen.getByText("Unknown")).toBeInTheDocument();
  });

  it("persists column visibility in localStorage", async () => {
    fetchLedgerQuery.mockResolvedValue({
      rows: [{ occurred_at: "2024-01-01", date: "2024-01-01", description: "Desc", vendor: "V", amount: 1, category: "Cat", account: "Operating", balance: 3, source_event_id: "evt-1" }],
      summary: { row_count: 1, start_balance: 0, end_balance: 0, total_in: 0, total_out: 0 },
      total_count: 1,
      has_more: false,
      next_offset: null,
    });
    fetchLedgerAccountDimensions.mockResolvedValue([]);
    fetchLedgerVendorDimensions.mockResolvedValue([]);

    const user = userEvent.setup();
    const view = renderPage();
    await screen.findByText("Desc");

    await user.click(screen.getByText("Columns"));
    await user.click(screen.getByLabelText("vendor"));

    expect(screen.queryByRole("columnheader", { name: "Vendor" })).not.toBeInTheDocument();
    view.unmount();

    renderPage();
    await screen.findByText("Desc");
    expect(screen.queryByRole("columnheader", { name: "Vendor" })).not.toBeInTheDocument();
  });

  it("loads more ledger rows and updates showing count", async () => {
    const user = userEvent.setup();
    fetchLedgerQuery.mockReset();
    fetchLedgerAccountDimensions.mockReset();
    fetchLedgerVendorDimensions.mockReset();

    const page1 = {
      rows: [
        {
          occurred_at: "2024-01-01",
          date: "2024-01-01",
          description: "Row 1",
          vendor: "Vendor 1",
          amount: -10,
          category: "Meals",
          account: "Operating",
          balance: 100,
          source_event_id: "evt-1",
        },
      ],
      summary: { row_count: 2, start_balance: 0, end_balance: 0, total_in: 0, total_out: 0 },
      total_count: 2,
      has_more: true,
      next_offset: 1,
    };
    const page2 = {
      rows: [
        {
          occurred_at: "2024-01-02",
          date: "2024-01-02",
          description: "Row 2",
          vendor: "Vendor 2",
          amount: -20,
          category: "Rent",
          account: "Operating",
          balance: 80,
          source_event_id: "evt-2",
        },
      ],
      summary: { row_count: 2, start_balance: 0, end_balance: 0, total_in: 0, total_out: 0 },
      total_count: 2,
      has_more: false,
      next_offset: null,
    };

    fetchLedgerQuery.mockImplementation((_businessId, query) =>
      Promise.resolve(query?.offset == 1 ? page2 : page1)
    );
    fetchLedgerAccountDimensions.mockResolvedValue([]);
    fetchLedgerVendorDimensions.mockResolvedValue([]);

    renderPage();
    await screen.findByText("Row 1");
    expect(screen.getAllByText("Showing 1 of 2").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: /Load more/i }));

    await waitFor(() => {
      expect(fetchLedgerQuery).toHaveBeenCalledWith(
        BIZ_ID,
        expect.objectContaining({ offset: 1 }),
        expect.anything()
      );
    });
  });


});
