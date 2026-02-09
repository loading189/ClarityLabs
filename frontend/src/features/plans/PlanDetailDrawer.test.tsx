import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import PlanDetailDrawer from "./PlanDetailDrawer";

const fetchBusinessMembers = vi.fn();
const getPlanDetail = vi.fn();
const refreshPlan = vi.fn();

vi.mock("../../api/businesses", () => ({
  fetchBusinessMembers: (...args: unknown[]) => fetchBusinessMembers(...args),
}));

vi.mock("../../api/plansV2", () => ({
  activatePlan: vi.fn(),
  addPlanNote: vi.fn(),
  assignPlan: vi.fn(),
  closePlan: vi.fn(),
  getPlanDetail: (...args: unknown[]) => getPlanDetail(...args),
  refreshPlan: (...args: unknown[]) => refreshPlan(...args),
}));

vi.mock("../../app/auth/AuthContext", () => ({
  useAuth: () => ({ logout: vi.fn() }),
}));

describe("PlanDetailDrawer", () => {
  it("renders the latest observation verdict and refreshes", async () => {
    fetchBusinessMembers.mockResolvedValue([]);
    getPlanDetail.mockResolvedValue({
      plan: {
        id: "plan-1",
        business_id: "biz-1",
        created_by_user_id: "user-1",
        title: "Plan title",
        intent: "Plan intent",
        status: "active",
        created_at: "2024-01-01T00:00:00Z",
        updated_at: "2024-01-01T00:00:00Z",
        activated_at: "2024-01-02T00:00:00Z",
        closed_at: null,
      },
      conditions: [],
      latest_observation: {
        id: "obs-1",
        plan_id: "plan-1",
        observed_at: "2024-01-03T00:00:00Z",
        evaluation_start: "2024-01-02",
        evaluation_end: "2024-01-03",
        signal_state: null,
        metric_value: 12,
        metric_baseline: 10,
        metric_delta: 2,
        verdict: "success",
        evidence_json: {},
        created_at: "2024-01-03T00:00:00Z",
      },
      observations: [
        {
          id: "obs-1",
          plan_id: "plan-1",
          observed_at: "2024-01-03T00:00:00Z",
          evaluation_start: "2024-01-02",
          evaluation_end: "2024-01-03",
          signal_state: null,
          metric_value: 12,
          metric_baseline: 10,
          metric_delta: 2,
          verdict: "success",
          evidence_json: {},
          created_at: "2024-01-03T00:00:00Z",
        },
      ],
      state_events: [],
    });
    refreshPlan.mockResolvedValue({
      observation: {
        id: "obs-2",
        plan_id: "plan-1",
        observed_at: "2024-01-05T00:00:00Z",
        evaluation_start: "2024-01-04",
        evaluation_end: "2024-01-05",
        signal_state: null,
        metric_value: 9,
        metric_baseline: 12,
        metric_delta: -3,
        verdict: "failure",
        evidence_json: {},
        created_at: "2024-01-05T00:00:00Z",
      },
      success_candidate: false,
    });

    render(
      <PlanDetailDrawer open planId="plan-1" businessId="biz-1" onClose={() => undefined} />
    );

    await waitFor(() => expect(getPlanDetail).toHaveBeenCalled());
    expect((await screen.findAllByText(/Metric baseline 10.00 → 12.00/i)).length).toBeGreaterThan(0);
    expect((await screen.findAllByText(/Success/i)).length).toBeGreaterThan(0);

    await userEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(refreshPlan).toHaveBeenCalled());
    expect((await screen.findAllByText(/Metric baseline 12.00 → 9.00/i)).length).toBeGreaterThan(0);
    expect((await screen.findAllByText(/Failure/i)).length).toBeGreaterThan(0);
  });
});
