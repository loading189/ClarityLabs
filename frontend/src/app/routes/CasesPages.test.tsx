import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import CaseCenterPage from "./CaseCenterPage";
import CaseDetailPage from "./CaseDetailPage";
import TodayPage from "./TodayPage";

const listCases = vi.fn();
const getCase = vi.fn();
const getCaseTimeline = vi.fn();
const assignCase = vi.fn();
const scheduleCaseReview = vi.fn();
const recomputeCase = vi.fn();
const listWorkItems = vi.fn();
const completeWorkItem = vi.fn();
const snoozeWorkItem = vi.fn();
const tickSystem = vi.fn();
const getLastTick = vi.fn();

vi.mock("../../api/cases", () => ({
  listCases: (...args: unknown[]) => listCases(...args),
  getCase: (...args: unknown[]) => getCase(...args),
  getCaseTimeline: (...args: unknown[]) => getCaseTimeline(...args),
  assignCase: (...args: unknown[]) => assignCase(...args),
  scheduleCaseReview: (...args: unknown[]) => scheduleCaseReview(...args),
  recomputeCase: (...args: unknown[]) => recomputeCase(...args),
}));

vi.mock("../../api/work", () => ({
  listWorkItems: (...args: unknown[]) => listWorkItems(...args),
  completeWorkItem: (...args: unknown[]) => completeWorkItem(...args),
  snoozeWorkItem: (...args: unknown[]) => snoozeWorkItem(...args),
}));

vi.mock("../../api/system", () => ({
  tickSystem: (...args: unknown[]) => tickSystem(...args),
  getLastTick: (...args: unknown[]) => getLastTick(...args),
}));

describe("Case pages", () => {
  it("renders case center list", async () => {
    listCases.mockResolvedValueOnce({ items: [{ id: "case-1", business_id: "biz-1", domain: "liquidity", primary_signal_type: "liquidity.runway_low", severity: "high", status: "open", opened_at: "2024-01-01T00:00:00Z", last_activity_at: "2024-01-02T00:00:00Z", closed_at: null, signal_count: 2 }], total: 1, page: 1, page_size: 25 });

    render(<MemoryRouter initialEntries={["/app/biz-1/cases"]}><Routes><Route path="/app/:businessId/cases" element={<CaseCenterPage />} /></Routes></MemoryRouter>);

    expect(await screen.findByText("Case Center")).toBeInTheDocument();
    expect(await screen.findByText("liquidity.runway_low")).toBeInTheDocument();
  });

  it("renders today work items and complete action", async () => {
    getLastTick.mockResolvedValue(null);
    listWorkItems.mockResolvedValue({
      items: [
        {
          id: "work-1",
          case_id: "case-1",
          business_id: "biz-1",
          type: "SLA_BREACH",
          priority: 100,
          status: "open",
          due_at: "2026-01-01T00:00:00Z",
          snoozed_until: null,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
          resolved_at: null,
          idempotency_key: "case-1:SLA_BREACH",
          case_severity: "high",
          case_domain: "liquidity",
          assigned_to: null,
        },
      ],
      total: 1,
    });
    completeWorkItem.mockResolvedValue({ ok: true });
    render(<MemoryRouter initialEntries={["/app/biz-1/today?status=open"]}><Routes><Route path="/app/:businessId/today" element={<TodayPage />} /></Routes></MemoryRouter>);

    expect(await screen.findByText("Advisor Today")).toBeInTheDocument();
    expect(await screen.findByText("SLA_BREACH")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Mark complete" }));
    await waitFor(() => expect(completeWorkItem).toHaveBeenCalledWith("biz-1", "work-1"));
  });

  it("refreshes queue and reloads work list", async () => {
    getLastTick.mockResolvedValue({ business_id: "biz-1", bucket: "2026-01-01", finished_at: "2026-01-01T00:00:00Z", result_summary: {} });
    listWorkItems.mockResolvedValue({ items: [], total: 0 });
    tickSystem.mockResolvedValue({ bucket: "2026-01-01" });

    render(<MemoryRouter initialEntries={["/app/biz-1/today?status=open"]}><Routes><Route path="/app/:businessId/today" element={<TodayPage />} /></Routes></MemoryRouter>);

    expect(await screen.findByRole("button", { name: "Refresh queue" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Refresh queue" }));

    await waitFor(() => expect(tickSystem).toHaveBeenCalledWith({ business_id: "biz-1", apply_recompute: false, materialize_work: true }));
    await waitFor(() => expect(listWorkItems).toHaveBeenCalledTimes(2));
  });

  it("renders case detail governance and timeline", async () => {
    getCase.mockResolvedValue({ case: { id: "case-1", business_id: "biz-1", domain: "liquidity", primary_signal_type: "liquidity.runway_low", severity: "high", status: "escalated", opened_at: "2024-01-01T00:00:00Z", last_activity_at: "2024-01-02T00:00:00Z", closed_at: null, signal_count: 2, assigned_to: "advisor-1", next_review_at: null, sla_due_at: "2024-01-03T00:00:00Z", sla_breached: true }, signals: [{ signal_id: "sig-1", signal_type: "liquidity.runway_low", status: "open", title: "Low runway", summary: "summary" }], actions: [], plans: [], ledger_anchors: [] });
    getCaseTimeline.mockResolvedValueOnce([{ id: "evt-1", event_type: "CASE_CREATED", payload_json: {}, created_at: "2024-01-01T00:00:00Z" }]);

    render(<MemoryRouter initialEntries={["/app/biz-1/cases/case-1"]}><Routes><Route path="/app/:businessId/cases/:caseId" element={<CaseDetailPage />} /></Routes></MemoryRouter>);

    expect(await screen.findByText("Case Detail")).toBeInTheDocument();
    expect(screen.getByText("Governance")).toBeInTheDocument();
    expect(screen.getByLabelText("Assigned to")).toBeInTheDocument();
    expect(screen.getByText(/CASE_CREATED/)).toBeInTheDocument();
  });
});
