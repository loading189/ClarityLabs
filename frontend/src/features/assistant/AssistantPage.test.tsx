import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { AppStateProvider } from "../../app/state/appState";
import AssistantPage from "./AssistantPage";

const fetchAssistantSummary = vi.fn();
const postAssistantAction = vi.fn();

vi.mock("../../api/assistantTools", () => ({
  fetchAssistantSummary: (...args: unknown[]) => fetchAssistantSummary(...args),
  postAssistantAction: (...args: unknown[]) => postAssistantAction(...args),
}));

function LocationDisplay() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

function renderAssistant(path = "/app/biz-1/assistant") {
  return render(
    <AppStateProvider>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route
            path="/app/:businessId/assistant"
            element={
              <>
                <LocationDisplay />
                <AssistantPage />
              </>
            }
          />
        </Routes>
      </MemoryRouter>
    </AppStateProvider>
  );
}

describe("AssistantPage", () => {
  beforeEach(() => {
    fetchAssistantSummary.mockResolvedValue({
      business_id: "biz-1",
      integrations: [],
      monitor_status: { stale: false, gated: false },
      open_signals: 0,
      uncategorized_count: 0,
      audit_events: [],
      top_vendors: [],
    });
    postAssistantAction.mockResolvedValue({ ok: true, result: {} });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("does not auto-navigate on load", async () => {
    renderAssistant();
    await waitFor(() => expect(fetchAssistantSummary).toHaveBeenCalled());
    expect(screen.getByTestId("location").textContent).toBe("/app/biz-1/assistant");
    expect(postAssistantAction).not.toHaveBeenCalled();
  });

  it("runs monitoring pulse via action button", async () => {
    const user = userEvent.setup();
    fetchAssistantSummary
      .mockResolvedValueOnce({
        business_id: "biz-1",
        integrations: [],
        monitor_status: { stale: true, gated: false },
        open_signals: 1,
        uncategorized_count: 2,
        audit_events: [],
        top_vendors: [],
      })
      .mockResolvedValueOnce({
        business_id: "biz-1",
        integrations: [],
        monitor_status: { stale: false, gated: false },
        open_signals: 1,
        uncategorized_count: 2,
        audit_events: [],
        top_vendors: [],
      });

    renderAssistant();
    const button = await screen.findByRole("button", { name: /run monitoring pulse/i });
    await user.click(button);

    await waitFor(() => expect(postAssistantAction).toHaveBeenCalledWith("biz-1", "run_pulse"));
    await screen.findByText("Fresh");
  });

  it("syncs integrations via action button", async () => {
    const user = userEvent.setup();
    fetchAssistantSummary.mockResolvedValue({
      business_id: "biz-1",
      integrations: [{ provider: "stripe", status: "connected" }],
      monitor_status: { stale: false, gated: false },
      open_signals: 0,
      uncategorized_count: 0,
      audit_events: [],
      top_vendors: [],
    });

    renderAssistant();
    const button = await screen.findByRole("button", { name: /sync integrations/i });
    await user.click(button);

    await waitFor(() => expect(postAssistantAction).toHaveBeenCalledWith("biz-1", "sync_integrations"));
  });
});
