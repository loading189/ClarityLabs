import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import CaseCenterPage from "./CaseCenterPage";
import CaseDetailPage from "./CaseDetailPage";

const listCases = vi.fn();
const getCase = vi.fn();
const getCaseTimeline = vi.fn();

vi.mock("../../api/cases", () => ({
  listCases: (...args: unknown[]) => listCases(...args),
  getCase: (...args: unknown[]) => getCase(...args),
  getCaseTimeline: (...args: unknown[]) => getCaseTimeline(...args),
}));

describe("Case pages", () => {
  it("renders case center list", async () => {
    listCases.mockResolvedValueOnce({
      items: [
        {
          id: "case-1",
          business_id: "biz-1",
          domain: "liquidity",
          primary_signal_type: "liquidity.runway_low",
          severity: "high",
          status: "open",
          opened_at: "2024-01-01T00:00:00Z",
          last_activity_at: "2024-01-02T00:00:00Z",
          closed_at: null,
          signal_count: 2,
        },
      ],
      total: 1,
      page: 1,
      page_size: 25,
    });

    render(
      <MemoryRouter initialEntries={["/app/biz-1/cases"]}>
        <Routes>
          <Route path="/app/:businessId/cases" element={<CaseCenterPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("Case Center")).toBeInTheDocument();
    expect(await screen.findByText("liquidity.runway_low")).toBeInTheDocument();
  });

  it("renders case detail timeline and evidence", async () => {
    getCase.mockResolvedValueOnce({
      case: {
        id: "case-1",
        business_id: "biz-1",
        domain: "liquidity",
        primary_signal_type: "liquidity.runway_low",
        severity: "high",
        status: "escalated",
        opened_at: "2024-01-01T00:00:00Z",
        last_activity_at: "2024-01-02T00:00:00Z",
        closed_at: null,
        signal_count: 2,
      },
      signals: [{ signal_id: "sig-1", signal_type: "liquidity.runway_low", status: "open", title: "Low runway", summary: "summary" }],
      actions: [],
      plans: [],
      ledger_anchors: [],
    });
    getCaseTimeline.mockResolvedValueOnce([
      { id: "evt-1", event_type: "CASE_CREATED", payload_json: {}, created_at: "2024-01-01T00:00:00Z" },
    ]);

    render(
      <MemoryRouter initialEntries={["/app/biz-1/cases/case-1"]}>
        <Routes>
          <Route path="/app/:businessId/cases/:caseId" element={<CaseDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("Case Detail")).toBeInTheDocument();
    await waitFor(() => expect(getCase).toHaveBeenCalled());
    expect(screen.getByText(/Low runway/)).toBeInTheDocument();
    expect(screen.getByText(/CASE_CREATED/)).toBeInTheDocument();
  });
});
