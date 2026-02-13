import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import AdvisorInboxPage from "./AdvisorInboxPage";

const fetchActionTriage = vi.fn();
const refreshActions = vi.fn();
const getPlanSummaries = vi.fn();

const actionDetailDrawer = vi.fn();

vi.mock("../features/actions/ActionDetailDrawer", () => ({
  default: (props: { open: boolean; action: { id: string } | null }) => {
    actionDetailDrawer(props);
    return props.open ? <div>Action Drawer Open: {props.action?.id}</div> : null;
  },
}));

vi.mock("../api/actions", () => ({
  fetchActionTriage: (...args: unknown[]) => fetchActionTriage(...args),
  refreshActions: (...args: unknown[]) => refreshActions(...args),
}));

vi.mock("../api/plansV2", () => ({
  getPlanSummaries: (...args: unknown[]) => getPlanSummaries(...args),
}));

vi.mock("../api/dataStatus", () => ({
  fetchDataStatus: vi.fn().mockResolvedValue({
    latest_event: { source: "plaid", occurred_at: new Date().toISOString() },
    open_signals: 1,
    open_actions: 1,
    ledger_rows: 1,
    uncategorized_txns: 1,
    last_sync_at: new Date().toISOString(),
  }),
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
  beforeEach(() => {
    actionDetailDrawer.mockClear();
    fetchActionTriage.mockReset();
    refreshActions.mockReset();
    getPlanSummaries.mockReset();
  });
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

    expect(await screen.findByText("Inbox")).toBeInTheDocument();
    await waitFor(() => expect(fetchActionTriage).toHaveBeenCalled());
    expect(screen.getByText("Categorize transactions")).toBeInTheDocument();
    expect(await screen.findByText("Active")).toBeInTheDocument();
    expect(await screen.findByText("Success")).toBeInTheDocument();
  });

  it("renders filters and updates the list when filters change", async () => {
    fetchActionTriage.mockResolvedValueOnce({
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
          source_signal_id: "signal-1",
          evidence_json: { signal_title: "Uncategorized volume" },
          rationale_json: null,
          resolution_reason: null,
          resolution_note: null,
          resolution_meta_json: null,
          resolved_at: null,
          assigned_to_user_id: "user-1",
          resolved_by_user_id: null,
          snoozed_until: null,
          assigned_to_user: { id: "user-1", email: "me@firm.com" },
          plan_id: null,
        },
        {
          id: "action-2",
          business_id: "biz-1",
          business_name: "Acme Co",
          action_type: "followup",
          title: "Review vendor anomaly",
          summary: "Watch list",
          priority: 3,
          status: "snoozed",
          created_at: "2024-02-02T00:00:00Z",
          due_at: null,
          source_signal_id: "signal-2",
          evidence_json: { signal_title: "Vendor spike" },
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
        },
      ],
      summary: { by_status: { open: 1, snoozed: 1 }, by_business: [] },
    });

    render(
      <MemoryRouter>
        <AdvisorInboxPage />
      </MemoryRouter>
    );

    expect(await screen.findByText("Categorize transactions")).toBeInTheDocument();
    expect(screen.getByText("Review vendor anomaly")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Assigned to me" }));
    expect(screen.getByText("Categorize transactions")).toBeInTheDocument();
    expect(screen.queryByText("Review vendor anomaly")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Snoozed" }));
    expect(screen.queryByText("Categorize transactions")).not.toBeInTheDocument();
    expect(screen.getByText("Review vendor anomaly")).toBeInTheDocument();
  });

  it("renders empty state with refresh actions CTA", async () => {
    fetchActionTriage.mockResolvedValueOnce({ actions: [], summary: { by_status: {}, by_business: [] } });
    refreshActions.mockResolvedValueOnce({ actions: [], summary: { by_status: {}, by_business: [] } });

    render(
      <MemoryRouter>
        <AdvisorInboxPage />
      </MemoryRouter>
    );

    expect(await screen.findByText("No actions in this queue yet.")).toBeInTheDocument();
    const refreshButton = screen.getByRole("button", { name: "Refresh Actions" });
    await waitFor(() => expect(refreshButton).toBeEnabled());
    await userEvent.click(refreshButton);
    await waitFor(() => expect(refreshActions).toHaveBeenCalledWith("biz-1"));
  });
  it("auto-opens requested action drawer after actions load", async () => {
    fetchActionTriage.mockResolvedValueOnce({
      actions: [
        {
          id: "action-2",
          business_id: "biz-1",
          business_name: "Acme Co",
          action_type: "followup",
          title: "Review vendor anomaly",
          summary: "Watch list",
          priority: 3,
          status: "open",
          created_at: "2024-02-02T00:00:00Z",
          due_at: null,
          source_signal_id: "signal-2",
          evidence_json: { signal_title: "Vendor spike" },
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
        },
      ],
      summary: { by_status: { open: 1 }, by_business: [] },
    });

    render(
      <MemoryRouter initialEntries={["/app/biz-1/advisor?action_id=action-2"]}>
        <AdvisorInboxPage />
      </MemoryRouter>
    );

    expect(await screen.findByText("Action Drawer Open: action-2")).toBeInTheDocument();
  });

});
