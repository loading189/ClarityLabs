import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import TransactionDetailDrawer from "./TransactionDetailDrawer";

const fetchTransactionDetail = vi.fn();

vi.mock("../../api/transactions", () => ({
  fetchTransactionDetail: (...args: unknown[]) => fetchTransactionDetail(...args),
}));

describe("TransactionDetailDrawer", () => {
  it("renders raw payload and processing sections", async () => {
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

    expect(await screen.findByText(/Raw event \/ ingestion/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Coffee Shop/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Processing assumptions/i)).toBeInTheDocument();
    expect(screen.getByText(/Direction derived from amount sign/i)).toBeInTheDocument();
    expect(screen.getByText(/Raw payload/i)).toBeInTheDocument();
  });
});
