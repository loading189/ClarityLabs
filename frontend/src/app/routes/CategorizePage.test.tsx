import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import CategorizePage from "./CategorizePage";

const fetchTxnsToCategorize = vi.fn();
const fetchCategories = vi.fn();
const saveCategorization = vi.fn();

vi.mock("../../api/dataStatus", () => ({
  fetchDataStatus: vi.fn().mockResolvedValue({
    latest_event: { source: "plaid", occurred_at: new Date().toISOString() },
    open_signals: 1,
    open_actions: 1,
    ledger_rows: 1,
    uncategorized_txns: 1,
    last_sync_at: new Date().toISOString(),
  }),
}));

vi.mock("../../api/categorize", () => ({
  fetchTxnsToCategorize: (...args: unknown[]) => fetchTxnsToCategorize(...args),
  fetchCategories: (...args: unknown[]) => fetchCategories(...args),
  saveCategorization: (...args: unknown[]) => saveCategorization(...args),
}));

describe("CategorizePage", () => {
  beforeEach(() => {
    fetchTxnsToCategorize.mockReset();
    fetchCategories.mockReset();
    saveCategorization.mockReset();
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  function renderPage(businessId = "11111111-1111-4111-8111-111111111111") {
    return render(
      <MemoryRouter initialEntries={[`/app/${businessId}/categorize`]}>
        <Routes>
          <Route path="/app/:businessId/categorize" element={<CategorizePage />} />
        </Routes>
      </MemoryRouter>
    );
  }

  it("renders uncategorized transactions from the API", async () => {
    fetchTxnsToCategorize.mockResolvedValue([
      {
        source_event_id: "evt-1",
        occurred_at: "2025-01-10T00:00:00.000Z",
        description: "Office Depot",
        amount: -42,
        direction: "outflow",
        account: "card",
        category_hint: "uncategorized",
        counterparty_hint: "Office Depot",
      },
    ]);
    fetchCategories.mockResolvedValue([
      {
        id: "cat-1",
        name: "Office Supplies",
        account_id: "acct-1",
        account_name: "Office Supplies",
      },
    ]);

    renderPage();

    const rows = await screen.findAllByText("Office Depot");
    expect(rows.length).toBeGreaterThan(0);
    expect(screen.getByText("Uncategorized")).toBeInTheDocument();
  });

  it("shows empty state when no uncategorized transactions remain", async () => {
    fetchTxnsToCategorize.mockResolvedValue([
      {
        source_event_id: "evt-2",
        occurred_at: "2025-01-12T00:00:00.000Z",
        description: "Payroll",
        amount: -1000,
        direction: "outflow",
        account: "checking",
        category_hint: "Payroll",
        category_name: "Payroll",
        category_id: "cat-2",
      },
    ]);
    fetchCategories.mockResolvedValue([
      {
        id: "cat-2",
        name: "Payroll",
        account_id: "acct-2",
        account_name: "Payroll",
      },
    ]);

    renderPage();

    expect(
      await screen.findByText("All caught up. No uncategorized transactions detected.")
    ).toBeInTheDocument();
  });

  it("applies a categorization and removes the transaction", async () => {
    fetchTxnsToCategorize.mockResolvedValue([
      {
        source_event_id: "evt-3",
        occurred_at: "2025-02-01T00:00:00.000Z",
        description: "Coffee Shop",
        amount: -5,
        direction: "outflow",
        account: "card",
        category_hint: "uncategorized",
      },
    ]);
    fetchCategories.mockResolvedValue([
      {
        id: "cat-3",
        name: "Meals",
        account_id: "acct-3",
        account_name: "Meals",
      },
    ]);
    saveCategorization.mockResolvedValue({ status: "ok", updated: true });

    renderPage();

    const rows = await screen.findAllByText("Coffee Shop");
    expect(rows.length).toBeGreaterThan(0);

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Apply" }));

    await waitFor(() => expect(saveCategorization).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryAllByText("Coffee Shop")).toHaveLength(0));
  });
});
