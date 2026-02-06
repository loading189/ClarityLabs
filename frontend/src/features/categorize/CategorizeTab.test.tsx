import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import CategorizeTab from "./CategorizeTab";

const getTxnsToCategorize = vi.fn();
const getCategories = vi.fn();
const getCategorizeMetrics = vi.fn();
const listCategoryRules = vi.fn();
const applyCategoryRule = vi.fn();
const getBrainVendors = vi.fn();
const fetchTransactionDetail = vi.fn();

let mockAppState = {
  dateRange: { start: "2025-01-01", end: "2025-01-31" },
  dataVersion: 0,
  bumpDataVersion: vi.fn(),
};

vi.mock("../../app/state/appState", () => ({
  useAppState: () => mockAppState,
}));

vi.mock("../../api/categorize", () => ({
  applyCategoryRule: (...args: unknown[]) => applyCategoryRule(...args),
  bulkApplyByMerchantKey: vi.fn(),
  createCategoryRule: vi.fn(),
  deleteCategoryRule: vi.fn(),
  getCategories: (...args: unknown[]) => getCategories(...args),
  getCategorizeMetrics: (...args: unknown[]) => getCategorizeMetrics(...args),
  getBrainVendors: (...args: unknown[]) => getBrainVendors(...args),
  getTxnsToCategorize: (...args: unknown[]) => getTxnsToCategorize(...args),
  listCategoryRules: (...args: unknown[]) => listCategoryRules(...args),
  previewCategoryRule: vi.fn(),
  saveCategorization: vi.fn(),
  updateCategoryRule: vi.fn(),
}));

vi.mock("../../api/transactions", () => ({
  fetchTransactionDetail: (...args: unknown[]) => fetchTransactionDetail(...args),
}));

describe("CategorizeTab", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    mockAppState = {
      dateRange: { start: "2025-01-01", end: "2025-01-31" },
      dataVersion: 0,
      bumpDataVersion: vi.fn(),
    };

    getTxnsToCategorize.mockReset();
    getCategories.mockReset();
    getCategorizeMetrics.mockReset();
    listCategoryRules.mockReset();
    applyCategoryRule.mockReset();
    getBrainVendors.mockReset();
    fetchTransactionDetail.mockReset();

    getTxnsToCategorize.mockResolvedValue([
      {
        source_event_id: "evt-1",
        occurred_at: "2025-01-10T15:00:00.000Z",
        description: "Coffee Shop",
        amount: -25,
        direction: "outflow",
        account: "card",
        category_hint: "uncategorized",
        merchant_key: "coffee-shop",
        suggested_category_id: "cat-1",
        confidence: 0.82,
      },
    ]);

    getCategories.mockResolvedValue([
      {
        id: "cat-1",
        name: "Meals",
        system_key: "meals",
        account_id: "acct-1",
        account_code: "6100",
        account_name: "Meals",
      },
      {
        id: "cat-2",
        name: "Travel",
        system_key: "travel",
        account_id: "acct-2",
        account_code: "6200",
        account_name: "Travel",
      },
    ]);

    getCategorizeMetrics.mockResolvedValue({
      total_events: 5,
      posted: 2,
      uncategorized: 3,
      suggestion_coverage: 2,
      brain_coverage: 1,
    });

    listCategoryRules.mockResolvedValue([
      {
        id: "rule-1",
        business_id: "biz-1",
        category_id: "cat-1",
        contains_text: "coffee",
        direction: "outflow",
        account: "card",
        priority: 1,
        active: true,
        created_at: "2025-01-01T00:00:00.000Z",
        last_run_at: null,
        last_run_updated_count: null,
      },
    ]);

    applyCategoryRule.mockResolvedValue({ rule_id: "rule-1", matched: 1, updated: 1 });
    getBrainVendors.mockResolvedValue([]);
    fetchTransactionDetail.mockResolvedValue({
      business_id: "biz-1",
      source_event_id: "evt-1",
      raw_event: {
        source: "bank",
        source_event_id: "evt-1",
        payload: {},
        occurred_at: "2025-01-10T15:00:00.000Z",
        created_at: "2025-01-10T15:01:00.000Z",
        processed_at: null,
      },
      normalized_txn: {
        source_event_id: "evt-1",
        occurred_at: "2025-01-10T15:00:00.000Z",
        date: "2025-01-10",
        description: "Coffee Shop",
        amount: -25,
        direction: "outflow",
        account: "card",
        category_hint: "uncategorized",
        counterparty_hint: "Coffee Shop",
        merchant_key: "coffee-shop",
      },
      vendor_normalization: { canonical_name: "Coffee Shop", source: "inferred" },
      categorization: null,
      processing_assumptions: [{ field: "direction", detail: "Derived from amount sign." }],
      ledger_context: null,
      audit_history: [],
      related_signals: [],
    });
  });

  it("loads APIs only once when app state rerenders with new dateRange identity", async () => {
    const view = render(
      <MemoryRouter>
        <CategorizeTab businessId="11111111-1111-4111-8111-111111111111" />
      </MemoryRouter>
    );

    await waitFor(() => expect(getTxnsToCategorize).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(getCategories).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(getCategorizeMetrics).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(getBrainVendors).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(listCategoryRules).toHaveBeenCalledTimes(1));

    mockAppState = {
      ...mockAppState,
      dateRange: { start: "2025-01-01", end: "2025-01-31" },
    };

    view.rerender(
      <MemoryRouter>
        <CategorizeTab businessId="11111111-1111-4111-8111-111111111111" />
      </MemoryRouter>
    );

    await waitFor(() => expect(getTxnsToCategorize).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(getCategories).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(getCategorizeMetrics).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(getBrainVendors).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(listCategoryRules).toHaveBeenCalledTimes(1));
  });

  it("updates selected category when filtered transactions force a new selected txn", async () => {
    getTxnsToCategorize.mockResolvedValue([
      {
        source_event_id: "evt-1",
        occurred_at: "2025-01-10T15:00:00.000Z",
        description: "Alpha Vendor",
        amount: -10,
        direction: "outflow",
        account: "card",
        category_hint: "uncategorized",
        merchant_key: "alpha",
        suggested_category_id: "cat-1",
        confidence: 0.7,
      },
      {
        source_event_id: "evt-2",
        occurred_at: "2025-01-12T15:00:00.000Z",
        description: "Beta Vendor",
        amount: -20,
        direction: "outflow",
        account: "card",
        category_hint: "uncategorized",
        merchant_key: "beta",
        suggested_category_id: "cat-2",
        confidence: 0.9,
      },
    ]);

    const view = render(
      <MemoryRouter>
        <CategorizeTab
          businessId="11111111-1111-4111-8111-111111111111"
          drilldown={{ search: "alpha" }}
        />
      </MemoryRouter>
    );

    const categorySelects = await screen.findAllByLabelText("Category");
    expect((categorySelects[0] as HTMLSelectElement).value).toBe("cat-1");

    view.rerender(
      <MemoryRouter>
        <CategorizeTab
          businessId="11111111-1111-4111-8111-111111111111"
          drilldown={{ search: "beta" }}
        />
      </MemoryRouter>
    );

    await waitFor(() => {
      const categoryInputs = screen.getAllByLabelText("Category");
      expect((categoryInputs[0] as HTMLSelectElement).value).toBe("cat-2");
    });
  });

  it("renders uncategorized list and opens detail on selection", async () => {
    const user = userEvent.setup();
    getTxnsToCategorize.mockResolvedValueOnce([
      {
        source_event_id: "evt-1",
        occurred_at: "2025-01-10T15:00:00.000Z",
        description: "Alpha Vendor",
        amount: -10,
        direction: "outflow",
        account: "card",
        category_hint: "uncategorized",
        merchant_key: "alpha",
      },
      {
        source_event_id: "evt-2",
        occurred_at: "2025-01-11T15:00:00.000Z",
        description: "Beta Vendor",
        amount: -20,
        direction: "outflow",
        account: "card",
        category_hint: "uncategorized",
        merchant_key: "beta",
      },
    ]);

    render(
      <MemoryRouter>
        <CategorizeTab businessId="11111111-1111-4111-8111-111111111111" />
      </MemoryRouter>
    );

    expect(await screen.findByRole("button", { name: /Select transaction Alpha Vendor/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Select transaction Beta Vendor/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Select transaction Beta Vendor/i }));
    await waitFor(() => expect(fetchTransactionDetail).toHaveBeenCalledWith(
      "11111111-1111-4111-8111-111111111111",
      "evt-2"
    ));
  });

  it("applies a rule and refreshes data", async () => {
    const onCategorizationChange = vi.fn();
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <CategorizeTab
          businessId="11111111-1111-4111-8111-111111111111"
          onCategorizationChange={onCategorizationChange}
        />
      </MemoryRouter>
    );

    await waitFor(() => expect(listCategoryRules).toHaveBeenCalledTimes(1));

    const applyButtons = await screen.findAllByRole("button", { name: "Apply now" });
    await user.click(applyButtons[0]);

    await waitFor(() =>
      expect(applyCategoryRule).toHaveBeenCalledWith(
        "11111111-1111-4111-8111-111111111111",
        "rule-1"
      )
    );
    await waitFor(() => expect(getTxnsToCategorize.mock.calls.length).toBeGreaterThanOrEqual(2));
    await waitFor(() => expect(getCategories.mock.calls.length).toBeGreaterThanOrEqual(2));
    await waitFor(() => expect(getCategorizeMetrics.mock.calls.length).toBeGreaterThanOrEqual(2));
    await waitFor(() => expect(listCategoryRules.mock.calls.length).toBeGreaterThanOrEqual(2));
    await waitFor(() => expect(onCategorizationChange).toHaveBeenCalled());
  });
});
