import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import TransactionDetailDrawer from "./TransactionDetailDrawer";

const fetchTransactionDetail = vi.fn();
const createCategoryRule = vi.fn();
const previewCategoryRule = vi.fn();
const applyCategoryRule = vi.fn();
const saveCategorization = vi.fn();
const getMonitorStatus = vi.fn();
const runMonitorPulse = vi.fn();

vi.mock("../../api/transactions", () => ({
  fetchTransactionDetail: (...args: unknown[]) => fetchTransactionDetail(...args),
}));

vi.mock("../../api/categorize", () => ({
  createCategoryRule: (...args: unknown[]) => createCategoryRule(...args),
  previewCategoryRule: (...args: unknown[]) => previewCategoryRule(...args),
  applyCategoryRule: (...args: unknown[]) => applyCategoryRule(...args),
  saveCategorization: (...args: unknown[]) => saveCategorization(...args),
}));

vi.mock("../../api/monitor", () => ({
  getMonitorStatus: (...args: unknown[]) => getMonitorStatus(...args),
  runMonitorPulse: (...args: unknown[]) => runMonitorPulse(...args),
}));

describe("TransactionDetailDrawer", () => {
  it("renders transaction audit sections", async () => {
    fetchTransactionDetail.mockResolvedValueOnce({
      business_id: "biz-1",
      source_event_id: "evt-1",
      raw_event: {
        source: "bank",
        source_event_id: "evt-1",
        payload: { transaction: { amount: -25, name: "Coffee Shop" } },
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
      suggested_category: null,
      rule_suggestion: null,
      processing_assumptions: [
        { field: "direction", detail: "Direction derived from amount sign." },
      ],
      ledger_context: null,
      audit_history: [],
      related_signals: [],
    });

    render(
      <MemoryRouter>
        <TransactionDetailDrawer
          open
          businessId="biz-1"
          sourceEventId="evt-1"
          onClose={() => undefined}
        />
      </MemoryRouter>
    );

    expect(await screen.findByRole("heading", { name: /Raw Event/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Normalized/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Categorization/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Related Signals/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Audit History/i })).toBeInTheDocument();
    expect(screen.getAllByText(/Coffee Shop/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Processing assumptions/i)).toBeInTheDocument();
    expect(screen.getByText(/Direction derived from amount sign/i)).toBeInTheDocument();
    expect(screen.getByText(/Raw payload/i)).toBeInTheDocument();
  });

  it("shows related signals when evidence matches", async () => {
    fetchTransactionDetail.mockResolvedValueOnce({
      business_id: "biz-1",
      source_event_id: "evt-2",
      raw_event: {
        source: "bank",
        source_event_id: "evt-2",
        payload: { transaction: { amount: -90, name: "Office Depot" } },
        occurred_at: "2025-01-11T15:00:00.000Z",
        created_at: "2025-01-11T15:01:00.000Z",
        processed_at: null,
      },
      normalized_txn: {
        source_event_id: "evt-2",
        occurred_at: "2025-01-11T15:00:00.000Z",
        date: "2025-01-11",
        description: "Office Depot",
        amount: -90,
        direction: "outflow",
        account: "card",
        category_hint: "supplies",
        counterparty_hint: "Office Depot",
        merchant_key: "office-depot",
      },
      vendor_normalization: { canonical_name: "Office Depot", source: "inferred" },
      categorization: null,
      suggested_category: null,
      rule_suggestion: null,
      processing_assumptions: [],
      ledger_context: null,
      audit_history: [],
      related_signals: [
        {
          signal_id: "sig-1",
          title: "Unusual outflow spike",
          severity: "high",
          status: "open",
          domain: "expense",
          updated_at: "2025-01-12T00:00:00.000Z",
          matched_on: "evidence_source_event_ids",
          window: { start: "2025-01-01", end: "2025-01-11" },
          facts: { latest_total: 900 },
          recommended_actions: [
            {
              action_id: "unusual_outflow_spike.review",
              label: "Review transactions",
              rationale: "Validate spikes",
            },
          ],
        },
      ],
    });

    render(
      <MemoryRouter>
        <TransactionDetailDrawer
          open
          businessId="biz-1"
          sourceEventId="evt-2"
          onClose={() => undefined}
        />
      </MemoryRouter>
    );

    expect(await screen.findByRole("heading", { name: /Related Signals/i })).toBeInTheDocument();
    expect(screen.getByText(/Unusual outflow spike/i)).toBeInTheDocument();
    expect(screen.getByText(/Matched on/i)).toBeInTheDocument();
  });

  it("creates and applies a rule from evidence with verification pulse", async () => {
    fetchTransactionDetail.mockResolvedValue({
      business_id: "biz-1",
      source_event_id: "evt-3",
      raw_event: {
        source: "bank",
        source_event_id: "evt-3",
        payload: { transaction: { amount: -120, name: "Vendor X" } },
        occurred_at: "2025-01-12T15:00:00.000Z",
        created_at: "2025-01-12T15:01:00.000Z",
        processed_at: null,
      },
      normalized_txn: {
        source_event_id: "evt-3",
        occurred_at: "2025-01-12T15:00:00.000Z",
        date: "2025-01-12",
        description: "Vendor X",
        amount: -120,
        direction: "outflow",
        account: "card",
        category_hint: "uncategorized",
        counterparty_hint: "Vendor X",
        merchant_key: "vendor-x",
      },
      vendor_normalization: { canonical_name: "Vendor X", source: "inferred" },
      categorization: null,
      suggested_category: {
        system_key: "supplies",
        category_id: "cat-1",
        category_name: "Supplies",
        source: "rule",
        confidence: 0.82,
        reason: "Match on description",
      },
      rule_suggestion: {
        contains_text: "Vendor X",
        category_id: "cat-1",
        category_name: "Supplies",
        direction: "outflow",
        account: "card",
      },
      processing_assumptions: [],
      ledger_context: null,
      audit_history: [],
      related_signals: [],
    });

    createCategoryRule.mockResolvedValue({ id: "rule-1" });
    previewCategoryRule.mockResolvedValue({ rule_id: "rule-1", matched: 3, samples: [] });
    applyCategoryRule.mockResolvedValue({ rule_id: "rule-1", matched: 3, updated: 2, audit_id: "audit-1" });
    getMonitorStatus.mockResolvedValue({
      business_id: "biz-1",
      last_pulse_at: null,
      newest_event_at: null,
      newest_event_source_event_id: null,
      open_count: 0,
      counts: { by_status: {}, by_severity: {} },
      gated: true,
      gating_reason: "Cooldown",
      gating_reason_code: "cooldown",
    });
    runMonitorPulse.mockResolvedValue({
      ran: true,
      last_pulse_at: new Date().toISOString(),
      newest_event_at: new Date().toISOString(),
      counts: { by_status: {}, by_severity: {} },
      touched_signal_ids: ["sig-2"],
    });

    render(
      <MemoryRouter>
        <TransactionDetailDrawer
          open
          businessId="biz-1"
          sourceEventId="evt-3"
          onClose={() => undefined}
        />
      </MemoryRouter>
    );

    await screen.findAllByRole("heading", { name: /Rule from Evidence/i });
    const createButton = screen.getByRole("button", { name: /Create rule from this transaction/i });
    await userEvent.click(createButton);

    expect(await screen.findByText(/Preview: 3 historical transactions/i)).toBeInTheDocument();

    const applyButton = screen.getByRole("button", { name: /Apply rule/i });
    await userEvent.click(applyButton);

    expect(await screen.findByText(/Monitoring is gated/i)).toBeInTheDocument();
    const forceButton = screen.getByRole("button", { name: /Re-run monitoring \(force\)/i });
    await userEvent.click(forceButton);

    expect(await screen.findByText(/sig-2/i)).toBeInTheDocument();
  });
});
