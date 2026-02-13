import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import SignalExplainPage from "./SignalExplainPage";

const fetchSignalExplain = vi.fn();
const createActionFromSignal = vi.fn();
const navigateSpy = vi.fn();

vi.mock("../../api/signalExplain", () => ({
  fetchSignalExplain: (...args: unknown[]) => fetchSignalExplain(...args),
}));

vi.mock("../../api/actions", () => ({
  createActionFromSignal: (...args: unknown[]) => createActionFromSignal(...args),
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => navigateSpy };
});

function renderPage(path = "/app/biz-1/signals/sig-1/explain") {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/app/:businessId/signals/:signalId/explain" element={<SignalExplainPage />} />
      </Routes>
    </MemoryRouter>
  );
}

describe("SignalExplainPage", () => {
  it("renders narrative and evidence and opens inbox for linked action", async () => {
    fetchSignalExplain.mockResolvedValueOnce({
      signal_id: "sig-1",
      business_id: "biz-1",
      title: "Expense Spike",
      status: "open",
      severity: "warning",
      linked_action_id: "act-1",
      narrative: { headline: "headline", why_it_matters: ["why"], what_changed: ["changed"] },
      detector: { domain: "expense", rule_id: "expense_spike_vendor", version: "1" },
      case_evidence: { window: { start: "2024-01-01", end: "2024-01-31" }, stats: { baseline_total: 1, current_total: 2, pct_change: 100 }, top_transactions: [], ledger_anchors: [] },
    });
    renderPage();
    expect(await screen.findByText("headline")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Open in Inbox" }));
    await waitFor(() => expect(navigateSpy).toHaveBeenCalledWith("/app/biz-1/inbox?action_id=act-1"));
  });

  it("creates action when linked action does not exist", async () => {
    fetchSignalExplain.mockResolvedValueOnce({
      signal_id: "sig-1", business_id: "biz-1", title: "Expense Spike", status: "open", severity: "warning", linked_action_id: null,
      narrative: { headline: "headline", why_it_matters: ["why"], what_changed: ["changed"] },
      detector: { domain: "expense", rule_id: "expense_spike_vendor", version: "1" },
      case_evidence: { window: { start: "2024-01-01", end: "2024-01-31" }, stats: { baseline_total: 1, current_total: 2, pct_change: 100 }, top_transactions: [], ledger_anchors: [] },
    });
    createActionFromSignal.mockResolvedValueOnce({ action_id: "act-2" });
    renderPage();
    await screen.findByText("headline");
    fireEvent.click(screen.getByRole("button", { name: "Create Action" }));
    await waitFor(() => expect(createActionFromSignal).toHaveBeenCalledWith("biz-1", "sig-1"));
    await waitFor(() => expect(navigateSpy).toHaveBeenCalledWith("/app/biz-1/inbox?action_id=act-2"));
  });
});
