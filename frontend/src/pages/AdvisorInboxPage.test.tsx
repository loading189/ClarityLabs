import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import AdvisorInboxPage from "./AdvisorInboxPage";

const fetchActionTriage = vi.fn();

vi.mock("../api/actions", () => ({
  fetchActionTriage: (...args: unknown[]) => fetchActionTriage(...args),
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
  it("renders the inbox with mocked data", async () => {
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
          assigned_to_user_id: null,
          resolved_by_user_id: null,
          snoozed_until: null,
          assigned_to_user: null,
        },
      ],
      summary: { by_status: { open: 1 }, by_business: [] },
    });

    render(
      <MemoryRouter>
        <AdvisorInboxPage />
      </MemoryRouter>
    );

    expect(await screen.findByText("Advisor Inbox")).toBeInTheDocument();
    await waitFor(() => expect(fetchActionTriage).toHaveBeenCalled());
    expect(screen.getByText("Categorize transactions")).toBeInTheDocument();
  });
});
