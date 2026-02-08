import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import ActionDetailDrawer from "./ActionDetailDrawer";

const fetchBusinessMembers = vi.fn();
const fetchActionEvents = vi.fn();
const getPlanDetail = vi.fn();
const refreshPlan = vi.fn();

vi.mock("../../api/actions", () => ({
  assignAction: vi.fn(),
  fetchActionEvents: (...args: unknown[]) => fetchActionEvents(...args),
  resolveAction: vi.fn(),
  snoozeAction: vi.fn(),
}));

vi.mock("../../api/businesses", () => ({
  fetchBusinessMembers: (...args: unknown[]) => fetchBusinessMembers(...args),
}));

vi.mock("../../api/plansV2", () => ({
  closePlan: vi.fn(),
  createPlan: vi.fn(),
  getPlanDetail: (...args: unknown[]) => getPlanDetail(...args),
  refreshPlan: (...args: unknown[]) => refreshPlan(...args),
}));

vi.mock("../../app/auth/AuthContext", () => ({
  useAuth: () => ({ logout: vi.fn() }),
}));

describe("ActionDetailDrawer", () => {
  const baseAction = {
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
    assigned_to_user_id: null,
    resolved_by_user_id: null,
    snoozed_until: null,
    assigned_to_user: null,
    plan_id: null,
  };

  it("shows create plan CTA when no plan exists", async () => {
    fetchBusinessMembers.mockResolvedValue([]);
    fetchActionEvents.mockResolvedValue([]);

    render(
      <ActionDetailDrawer
        open
        action={baseAction}
        onClose={() => undefined}
      />
    );

    expect(await screen.findByText("Create a remediation plan")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create Plan" })).toBeInTheDocument();
  });

  it("renders plan summary and refreshes observations", async () => {
    fetchBusinessMembers.mockResolvedValue([]);
    fetchActionEvents.mockResolvedValue([]);
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
        observed_at: "2024-02-01T00:00:00Z",
        evaluation_start: "2024-02-01",
        evaluation_end: "2024-02-01",
        signal_state: null,
        metric_value: 10,
        metric_baseline: 8,
        metric_delta: 2,
        verdict: "success",
        evidence_json: {},
        created_at: "2024-02-01T00:00:00Z",
      },
      observations: [
        {
          id: "obs-1",
          plan_id: "plan-1",
          observed_at: "2024-02-01T00:00:00Z",
          evaluation_start: "2024-02-01",
          evaluation_end: "2024-02-01",
          signal_state: null,
          metric_value: 10,
          metric_baseline: 8,
          metric_delta: 2,
          verdict: "success",
          evidence_json: {},
          created_at: "2024-02-01T00:00:00Z",
        },
      ],
      state_events: [],
    });
    refreshPlan.mockResolvedValue({
      observation: {
        id: "obs-2",
        plan_id: "plan-1",
        observed_at: "2024-02-02T00:00:00Z",
        evaluation_start: "2024-02-02",
        evaluation_end: "2024-02-02",
        signal_state: null,
        metric_value: 7,
        metric_baseline: 10,
        metric_delta: -3,
        verdict: "failure",
        evidence_json: {},
        created_at: "2024-02-02T00:00:00Z",
      },
      success_candidate: false,
    });

    render(
      <ActionDetailDrawer
        open
        action={{ ...baseAction, plan_id: "plan-1" }}
        onClose={() => undefined}
      />
    );

    expect(await screen.findByText("Plan title")).toBeInTheDocument();
    const summary = await screen.findByTestId("plan-observation-summary");
    expect(summary).toHaveTextContent("Metric baseline 8.00 → 10.00");
    expect(screen.getByRole("button", { name: "View Plan" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(refreshPlan).toHaveBeenCalled());
    await waitFor(() =>
      expect(screen.getByTestId("plan-observation-summary")).toHaveTextContent(
        "Metric baseline 10.00 → 7.00"
      )
    );
  });
});
