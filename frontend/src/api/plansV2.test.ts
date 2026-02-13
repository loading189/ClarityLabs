import { describe, expect, it, vi } from "vitest";

const apiPost = vi.fn();

vi.mock("./client", () => ({
  apiGet: vi.fn(),
  apiPost: (...args: unknown[]) => apiPost(...args),
}));

import { createPlan } from "./plansV2";

describe("plansV2.createPlan", () => {
  it("posts to /api/plans with business_id query param and required body", async () => {
    const payload = {
      business_id: "biz-1",
      title: "Fix cash flow",
      intent: "Reduce volatility in weekly cash flow",
      source_action_id: "action-1",
      conditions: [
        {
          type: "signal_resolved" as const,
          signal_id: "signal-1",
          baseline_window_days: 0,
          evaluation_window_days: 14,
          direction: "resolve" as const,
        },
      ],
    };

    apiPost.mockResolvedValue({ plan: { id: "plan-1" } });

    await createPlan(payload);

    expect(apiPost).toHaveBeenCalledWith("/api/plans?business_id=biz-1", payload);
  });
});
