import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import PlanDetailDrawer from "./PlanDetailDrawer";

const fetchBusinessMembers = vi.fn();
const getPlanDetail = vi.fn();

vi.mock("../../api/businesses", () => ({
  fetchBusinessMembers: (...args: unknown[]) => fetchBusinessMembers(...args),
}));

vi.mock("../../api/plansV2", () => ({
  activatePlan: vi.fn(),
  addPlanNote: vi.fn(),
  assignPlan: vi.fn(),
  closePlan: vi.fn(),
  getPlanDetail: (...args: unknown[]) => getPlanDetail(...args),
  refreshPlan: vi.fn(),
}));

describe("PlanDetailDrawer", () => {
  it("renders the latest observation verdict", async () => {
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
      state_events: [],
    });

    render(
      <PlanDetailDrawer
        open
        planId="plan-1"
        businessId="biz-1"
        onClose={() => undefined}
      />
    );

    await waitFor(() => expect(getPlanDetail).toHaveBeenCalled());
    expect(screen.getByText(/Verdict: success/i)).toBeInTheDocument();
  });
});
