import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import ActionDetailDrawer from "./ActionDetailDrawer";

const fetchBusinessMembers = vi.fn();
const fetchActionEvents = vi.fn();
const createPlan = vi.fn();

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
  createPlan: (...args: unknown[]) => createPlan(...args),
}));

vi.mock("../plans/PlanDetailDrawer", () => ({
  default: () => null,
}));

describe("ActionDetailDrawer", () => {
  afterEach(() => {
    cleanup();
    createPlan.mockReset();
  });
  it("renders Create Plan when no plan exists", async () => {
    fetchBusinessMembers.mockResolvedValue([]);
    fetchActionEvents.mockResolvedValue([]);

    render(
      <MemoryRouter>
        <ActionDetailDrawer
          open
          action={{
            id: "action-1",
            business_id: "biz-1",
            action_type: "fix_mapping",
            title: "Categorize",
            summary: "Summary",
            priority: 3,
            status: "open",
            created_at: "2024-01-01T00:00:00Z",
            updated_at: "2024-01-01T00:00:00Z",
            idempotency_key: "key",
          }}
          onClose={() => undefined}
        />
      </MemoryRouter>
    );

    expect(await screen.findByText("Create Plan")).toBeInTheDocument();
  });

  it("creates a plan from an action with signal condition", async () => {
    fetchBusinessMembers.mockResolvedValue([]);
    fetchActionEvents.mockResolvedValue([]);
    createPlan.mockResolvedValue({ plan: { id: "plan-1" } });

    render(
      <MemoryRouter>
        <ActionDetailDrawer
          open
          action={{
            id: "action-2",
            business_id: "biz-2",
            action_type: "investigate",
            title: "Investigate",
            summary: "Summary",
            priority: 3,
            status: "open",
            created_at: "2024-01-01T00:00:00Z",
            updated_at: "2024-01-01T00:00:00Z",
            idempotency_key: "key",
            source_signal_id: "signal-9",
          }}
          onClose={() => undefined}
        />
      </MemoryRouter>
    );

    fireEvent.change(screen.getAllByPlaceholderText("Document the plan intent and why it matters")[0], {
      target: { value: "Do the thing" },
    });
    fireEvent.click(screen.getAllByText("Create Plan")[0]);

    await waitFor(() => expect(createPlan).toHaveBeenCalled());
    expect(createPlan).toHaveBeenCalledWith(
      expect.objectContaining({
        business_id: "biz-2",
        title: "Investigate",
        intent: "Do the thing",
        source_action_id: "action-2",
        primary_signal_id: "signal-9",
        conditions: [
          expect.objectContaining({
            type: "signal_resolved",
            signal_id: "signal-9",
            evaluation_window_days: 14,
            direction: "resolve",
          }),
        ],
      })
    );
  });
});
