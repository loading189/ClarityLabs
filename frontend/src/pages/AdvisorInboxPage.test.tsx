import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import AdvisorInboxPage from "./AdvisorInboxPage";

const fetchActionTriage = vi.fn();
const getPlanSummaries = vi.fn();

vi.mock("../api/actions", () => ({
  fetchActionTriage: (...args: unknown[]) => fetchActionTriage(...args),
}));

vi.mock("../api/plansV2", () => ({
  getPlanSummaries: (...args: unknown[]) => getPlanSummaries(...args),
}));

vi.mock("../app/auth/AuthContext", () => ({
  useAuth: () => ({ user: { id: "user-1", email: "me@firm.com" }, logout: vi.fn() }),
}));

vi.mock("../hooks/useBusinessesMine", () => ({
  useBusinessesMine: () => ({
    businesses: [
      { business_id: "biz-1", business_name: "Acme Co", role: "advisor" },
      { business_id: "biz-2", business_name: "Beacon LLC", role: "viewer" },
    ],
    loading: false,
    error: null,
    reload: vi.fn(),
  }),
}));

describe("AdvisorInboxPage", () => {
  it("renders plan status and latest verdict when present", async () => {
    fetchActionTriage.mockResolvedValue({
      actions: [
        {
          id: "action-1",
          business_id: "biz-1",
          business_name: "Acme Co",
          action_type: "fix_mapping",
          title: "Categorize transactions",
          summary: "Needs attention",
          priority: 4,
          status: "open",
          created_at: "2024-02-01T00:00:00Z",
          due_at: null,
          source_signal_id: null,
          evidence_json: null,
          rationale_json: null,
          resolution_reason: null,
          resolution_note: null,
          resolution_meta_json: null,
          resolved_at: null,
          assigned_to_user_id: "user-1",
          resolved_by_user_id: null,
          snoozed_until: null,
          assigned_to_user: { id: "user-1", email: "me@firm.com" },
          plan_id: "plan-1",
        },
      ],
      summary: { by_status: { open: 1 }, by_business: [] },
    });
    getPlanSummaries.mockResolvedValue([
      {
        id: "plan-1",
        business_id: "biz-1",
        title: "Plan title",
        status: "active",
        assigned_to_user_id: "user-1",
        latest_observation: {
          id: "obs-1",
          plan_id: "plan-1",
          observed_at: "2024-02-02T00:00:00Z",
          evaluation_start: "2024-02-01",
          evaluation_end: "2024-02-02",
          signal_state: null,
          metric_value: 12,
          metric_baseline: 10,
          metric_delta: 2,
          verdict: "success",
          evidence_json: {},
          created_at: "2024-02-02T00:00:00Z",
        },
      },
    ]);

    render(
      <MemoryRouter>
        <AdvisorInboxPage />
      </MemoryRouter>
    );

    expect(await screen.findByText("Advisor Inbox")).toBeInTheDocument();
    await waitFor(() => expect(fetchActionTriage).toHaveBeenCalled());
    expect(screen.getByText("Categorize transactions")).toBeInTheDocument();
    expect(await screen.findByText("Active")).toBeInTheDocument();
    expect(await screen.findByText("Success")).toBeInTheDocument();
  });
});
