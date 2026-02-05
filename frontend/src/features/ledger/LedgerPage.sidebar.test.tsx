import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import LedgerPage from "./LedgerPage";
import { AppStateProvider } from "../../app/state/appState";

const fetchLedgerQuery = vi.fn();
const fetchLedgerAccountDimensions = vi.fn();
const fetchLedgerVendorDimensions = vi.fn();

vi.mock("../../api/ledger", () => ({
  fetchLedgerQuery: (...args: unknown[]) => fetchLedgerQuery(...args),
  fetchLedgerAccountDimensions: (...args: unknown[]) => fetchLedgerAccountDimensions(...args),
  fetchLedgerVendorDimensions: (...args: unknown[]) => fetchLedgerVendorDimensions(...args),
}));

const BIZ_ID = "11111111-1111-1111-1111-111111111111";

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
});

describe("LedgerPage sidebar", () => {
  it("loads accounts/vendors dimensions", async () => {
    fetchLedgerQuery.mockResolvedValue({ rows: [], summary: { row_count: 0, start_balance: 0, end_balance: 0, total_in: 0, total_out: 0 } });
    fetchLedgerAccountDimensions.mockResolvedValue([{ account: "Operating", label: "Operating", count: 2, total: 100 }]);
    fetchLedgerVendorDimensions.mockResolvedValue([{ vendor: "Acme", count: 2, total: -50 }]);

    renderPage();
    await waitFor(() => expect(fetchLedgerAccountDimensions).toHaveBeenCalled());
    expect(await screen.findByText(/Operating/)).toBeInTheDocument();
  });

  it("clicking account filters ledger API call", async () => {
    fetchLedgerQuery.mockResolvedValue({ rows: [], summary: { row_count: 0, start_balance: 0, end_balance: 0, total_in: 0, total_out: 0 } });
    fetchLedgerAccountDimensions.mockResolvedValue([{ account: "Operating", label: "Operating", count: 2, total: 100 }]);
    fetchLedgerVendorDimensions.mockResolvedValue([]);

    renderPage();
    await screen.findByText("Operating");
    const user = userEvent.setup();
    await user.click(screen.getAllByRole("button", { name: /Operating/ })[0]);

    await waitFor(() => {
      const calls = fetchLedgerQuery.mock.calls;
      expect(calls[calls.length - 1][1].account).toEqual(["Operating"]);
    });
  });

  it("clicking vendor filters ledger API call", async () => {
    fetchLedgerQuery.mockResolvedValue({ rows: [], summary: { row_count: 0, start_balance: 0, end_balance: 0, total_in: 0, total_out: 0 } });
    fetchLedgerAccountDimensions.mockResolvedValue([]);
    fetchLedgerVendorDimensions.mockResolvedValue([{ vendor: "Acme", count: 2, total: -50 }]);

    renderPage();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Vendors/ }));
    await user.click(await screen.findByRole("button", { name: /Acme/ }));

    await waitFor(() => {
      const calls = fetchLedgerQuery.mock.calls;
      expect(calls[calls.length - 1][1].vendor).toEqual(["Acme"]);
    });
  });

  it("query params restore state", async () => {
    fetchLedgerQuery.mockResolvedValue({ rows: [], summary: { row_count: 0, start_balance: 0, end_balance: 0, total_in: 0, total_out: 0 } });
    fetchLedgerAccountDimensions.mockResolvedValue([]);
    fetchLedgerVendorDimensions.mockResolvedValue([]);

    renderPage(`/app/${BIZ_ID}/ledger?account=Operating&vendor=Acme%20Inc&q=rent`);

    await waitFor(() => expect(fetchLedgerQuery).toHaveBeenCalled());
    const call = fetchLedgerQuery.mock.calls[0][1];
    expect(call.account).toEqual(["Operating"]);
    expect(call.vendor).toEqual(["Acme Inc"]);
    expect(call.search).toBe("rent");
  });
});
