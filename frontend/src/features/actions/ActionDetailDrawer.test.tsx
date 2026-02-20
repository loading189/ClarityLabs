import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import type { ActionItem, ActionTriageItem } from "../../api/actions";
import ActionDetailDrawer from "./ActionDetailDrawer";

type ActionDetailFixture = (ActionItem | ActionTriageItem) & {
  business_name?: string;
};

const fetchBusinessMembers = vi.fn();
const fetchActionEvents = vi.fn();
const getPlanDetail = vi.fn();
const refreshPlan = vi.fn();
const createPlanFromAction = vi.fn();
const updateActionStatus = vi.fn();

vi.mock("../../api/actions", () => ({
  assignAction: vi.fn(),
  fetchActionEvents: (...args: unknown[]) => fetchActionEvents(...args),
  updateActionStatus: (...args: unknown[]) => updateActionStatus(...args),
}));

vi.mock("../../api/businesses", () => ({
  fetchBusinessMembers: (...args: unknown[]) => fetchBusinessMembers(...args),
}));

vi.mock("../../api/plansV2", () => ({
  closePlan: vi.fn(),
  createPlanFromAction: (...args: unknown[]) => createPlanFromAction(...args),
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
  } satisfies ActionDetailFixture;

  it("Start Plan calls createPlanFromAction", async () => {
    fetchBusinessMembers.mockResolvedValue([]);
    fetchActionEvents.mockResolvedValue([]);
    createPlanFromAction.mockResolvedValue({ plan_id: "plan-1", created: true });
    getPlanDetail.mockResolvedValue({
      plan: {
        id: "plan-1",
        business_id: "biz-1",
        created_by_user_id: "user-1",
        title: "Plan title",
        intent: "Plan intent",
        status: "draft",
        created_at: "2024-01-01T00:00:00Z",
        updated_at: "2024-01-01T00:00:00Z",
      },
      conditions: [],
      latest_observation: null,
      observations: [],
      state_events: [],
    });

    render(
      <MemoryRouter>
        <ActionDetailDrawer open action={baseAction} onClose={() => undefined} />
      </MemoryRouter>
    );

    await userEvent.click(await screen.findByRole("button", { name: "Start Plan" }));

    await waitFor(() => expect(createPlanFromAction).toHaveBeenCalledWith("biz-1", "action-1"));
  });

  it("shows Open Plan when action already has plan", async () => {
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
      },
      conditions: [],
      latest_observation: null,
      observations: [],
      state_events: [],
    });

    render(
      <MemoryRouter>
        <ActionDetailDrawer open action={{ ...baseAction, plan_id: "plan-1" }} onClose={() => undefined} />
      </MemoryRouter>
    );

    expect(await screen.findByRole("button", { name: "Open Plan" })).toBeInTheDocument();
  });

  it("status change triggers update call", async () => {
    fetchBusinessMembers.mockResolvedValue([]);
    fetchActionEvents.mockResolvedValue([]);
    updateActionStatus.mockResolvedValue({ ...baseAction, status: "done" });

    render(
      <MemoryRouter>
        <ActionDetailDrawer open action={baseAction} onClose={() => undefined} />
      </MemoryRouter>
    );

    const doneButtons = await screen.findAllByRole("button", { name: "Done" });
    await userEvent.click(doneButtons[0]);
    await waitFor(() => expect(updateActionStatus).toHaveBeenCalledWith("biz-1", "action-1", { status: "done", note: undefined }));
  });
});
