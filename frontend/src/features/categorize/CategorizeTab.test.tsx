import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import CategorizeTab from "./CategorizeTab";

const getTxnsToCategorize = vi.fn().mockResolvedValue([
  {
    source_event_id: "evt-1",
    occurred_at: new Date().toISOString(),
    description: "Coffee Shop",
    amount: -25.0,
    direction: "outflow",
    account: "card",
    category_hint: "uncategorized",
    merchant_key: "coffee shop",
    suggested_category_id: "cat-1",
    confidence: 0.82,
  },
]);
const getCategories = vi.fn().mockResolvedValue([
  {
    id: "cat-1",
    name: "Meals",
    system_key: "meals",
    account_id: "acct-1",
    account_code: "6100",
    account_name: "Meals",
  },
]);
const getCategorizeMetrics = vi.fn().mockResolvedValue({
  total_events: 5,
  posted: 2,
  uncategorized: 3,
  suggestion_coverage: 2,
  brain_coverage: 1,
});
const listCategoryRules = vi.fn().mockResolvedValue([
  {
    id: "rule-1",
    business_id: "biz-1",
    category_id: "cat-1",
    contains_text: "coffee",
    direction: "outflow",
    account: "card",
    priority: 1,
    active: true,
    created_at: new Date().toISOString(),
    last_run_at: null,
    last_run_updated_count: null,
  },
]);
const applyCategoryRule = vi.fn().mockResolvedValue({
  rule_id: "rule-1",
  matched: 1,
  updated: 1,
});

vi.mock("../../api/categorize", () => ({
  applyCategoryRule: (...args: unknown[]) => applyCategoryRule(...args),
  bulkApplyByMerchantKey: vi.fn(),
  deleteCategoryRule: vi.fn(),
  getCategories: (...args: unknown[]) => getCategories(...args),
  getCategorizeMetrics: (...args: unknown[]) => getCategorizeMetrics(...args),
  getTxnsToCategorize: (...args: unknown[]) => getTxnsToCategorize(...args),
  listCategoryRules: (...args: unknown[]) => listCategoryRules(...args),
  previewCategoryRule: vi.fn(),
  saveCategorization: vi.fn(),
  updateCategoryRule: vi.fn(),
}));

describe("CategorizeTab", () => {
  beforeEach(() => {
    getTxnsToCategorize.mockClear();
    getCategories.mockClear();
    getCategorizeMetrics.mockClear();
    listCategoryRules.mockClear();
    applyCategoryRule.mockClear();
  });

  it("applies a rule and refreshes data", async () => {
    const onCategorizationChange = vi.fn();
    const user = userEvent.setup();
    render(
      <CategorizeTab
        businessId="biz-1"
        onCategorizationChange={onCategorizationChange}
      />
    );

    await waitFor(() => expect(listCategoryRules).toHaveBeenCalledTimes(1));

    const applyButton = await screen.findByRole("button", { name: "Apply now" });
    await user.click(applyButton);

    await waitFor(() => expect(applyCategoryRule).toHaveBeenCalledWith("biz-1", "rule-1"));
    await waitFor(() => expect(getTxnsToCategorize).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(getCategories).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(getCategorizeMetrics).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(listCategoryRules).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(onCategorizationChange).toHaveBeenCalled());
  });
});
