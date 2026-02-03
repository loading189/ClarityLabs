import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TransactionsTab } from "./TransactionsTab";

const refresh = vi.fn().mockResolvedValue(undefined);
const getCategories = vi.fn().mockResolvedValue([
  {
    id: "cat-1",
    name: "Utilities",
    system_key: "utilities",
    account_id: "acct-1",
    account_code: "6000",
    account_name: "Utilities",
  },
]);
const saveCategorization = vi.fn().mockResolvedValue({ status: "ok" });

vi.mock("../../hooks/useTransactions", () => ({
  useTransactions: () => ({
    data: {
      business_id: "biz-1",
      name: "Demo Biz",
      as_of: new Date().toISOString(),
      count: 1,
      transactions: [
        {
          id: "txn-1",
          source_event_id: "evt-1",
          occurred_at: new Date().toISOString(),
          date: "2024-01-01",
          description: "Coffee Shop",
          amount: -12.34,
          direction: "outflow",
          account: "card",
          category: "Utilities",
          counterparty_hint: "coffee",
        },
      ],
    },
    loading: false,
    err: null,
    refresh,
  }),
}));

vi.mock("../../api/categorize", () => ({
  bulkApplyByMerchantKey: vi.fn(),
  createCategoryRule: vi.fn(),
  forgetBrainVendor: vi.fn(),
  getBrainVendor: vi.fn(),
  getCategories: (...args: unknown[]) => getCategories(...args),
  saveCategorization: (...args: unknown[]) => saveCategorization(...args),
  setBrainVendor: vi.fn(),
}));

describe("TransactionsTab", () => {
  beforeEach(() => {
    refresh.mockClear();
    getCategories.mockClear();
    saveCategorization.mockClear();
  });

  it("refreshes after saving a categorization", async () => {
    const onCategorizationChange = vi.fn();
    const user = userEvent.setup();
    render(
      <TransactionsTab
        businessId="biz-1"
        onCategorizationChange={onCategorizationChange}
      />
    );

    await waitFor(() => expect(getCategories).toHaveBeenCalled());

    const txnRow = screen.getByRole("button", {
      name: /Open actions for Coffee Shop/i,
    });
    await user.click(txnRow);

    const saveButton = screen.getByRole("button", { name: /Save categorization/i });
    await user.click(saveButton);

    await waitFor(() => expect(saveCategorization).toHaveBeenCalled());
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    await waitFor(() => expect(onCategorizationChange).toHaveBeenCalled());
  });

  it("clears drilldown filters and notifies the parent", async () => {
    const onClearDrilldown = vi.fn();
    const user = userEvent.setup();
    render(
      <TransactionsTab
        businessId="biz-1"
        drilldown={{
          direction: "outflow",
          category_id: "Utilities",
          search: "coffee",
          date_preset: "7d",
          merchant_key: "coffee shop",
        }}
        onClearDrilldown={onClearDrilldown}
      />
    );

    await waitFor(() => {
      const inputs = screen.getAllByPlaceholderText("Search description or vendor…");
      expect(inputs.some((input) => (input as HTMLInputElement).value === "coffee")).toBe(true);
    });
    const searchInput =
      screen
        .getAllByPlaceholderText("Search description or vendor…")
        .find((input) => (input as HTMLInputElement).value === "coffee") ??
      screen.getAllByPlaceholderText("Search description or vendor…")[0];

    await waitFor(() => {
      const selects = screen.getAllByRole("combobox");
      expect(selects.some((select) => (select as HTMLSelectElement).value === "outflow")).toBe(true);
      expect(selects.some((select) => (select as HTMLSelectElement).value === "Utilities")).toBe(true);
    });
    const selects = screen.getAllByRole("combobox");
    const directionSelect =
      selects.find((select) => (select as HTMLSelectElement).value === "outflow") ?? selects[0];
    const categorySelect =
      selects.find((select) => (select as HTMLSelectElement).value === "Utilities") ??
      selects[1];
    expect(screen.getAllByText(/Merchant: coffee shop/i).length).toBeGreaterThan(0);

    const clearButton = screen.getByRole("button", { name: /Clear drilldown/i });
    await user.click(clearButton);

    expect(onClearDrilldown).toHaveBeenCalled();
    expect(searchInput).toHaveValue("");
    expect(directionSelect).toHaveValue("all");
    expect(categorySelect).toHaveValue("all");
    expect(onClearDrilldown).toHaveBeenCalled();
  });
});
