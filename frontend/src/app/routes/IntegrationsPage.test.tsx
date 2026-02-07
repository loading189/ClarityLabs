import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import IntegrationsPage from "./IntegrationsPage";

const listIntegrationConnections = vi.fn();
const syncIntegration = vi.fn();
const replayIntegration = vi.fn();
const disableIntegration = vi.fn();
const enableIntegration = vi.fn();
const disconnectIntegration = vi.fn();
const createPlaidLinkToken = vi.fn();
const exchangePlaidPublicToken = vi.fn();

vi.mock("../../api/integrationConnections", () => ({
  listIntegrationConnections: (...args: unknown[]) => listIntegrationConnections(...args),
  syncIntegration: (...args: unknown[]) => syncIntegration(...args),
  replayIntegration: (...args: unknown[]) => replayIntegration(...args),
  disableIntegration: (...args: unknown[]) => disableIntegration(...args),
  enableIntegration: (...args: unknown[]) => enableIntegration(...args),
  disconnectIntegration: (...args: unknown[]) => disconnectIntegration(...args),
}));
vi.mock("../../api/plaid", () => ({
  createPlaidLinkToken: (...args: unknown[]) => createPlaidLinkToken(...args),
  exchangePlaidPublicToken: (...args: unknown[]) => exchangePlaidPublicToken(...args),
}));

function renderPage(path = "/app/biz-1/integrations") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/app/:businessId/integrations" element={<IntegrationsPage />} />
      </Routes>
    </MemoryRouter>
  );
}

describe("IntegrationsPage", () => {
  beforeEach(() => {
    listIntegrationConnections.mockResolvedValue([
      {
        id: "conn-1",
        business_id: "biz-1",
        provider: "plaid",
        status: "connected",
        is_enabled: true,
        last_sync_at: "2025-01-01T00:00:00Z",
        last_success_at: "2025-01-01T00:00:00Z",
        last_error_at: null,
        last_cursor: "cursor-2",
        last_processed_source_event_id: "plaid:txn-1",
        last_error: null,
      },
    ]);
    createPlaidLinkToken.mockResolvedValue({ link_token: "link-1" });
    exchangePlaidPublicToken.mockResolvedValue({ connection: { provider: "plaid" } });
    syncIntegration.mockResolvedValue({ provider: "plaid", inserted: 1, skipped: 0 });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders connection status and triggers connect + sync", async () => {
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByText(/connections/i)).toBeInTheDocument();
    expect(await screen.findByText(/connected/i)).toBeInTheDocument();

    const input = screen.getByPlaceholderText(/paste plaid public_token/i);
    await user.type(input, "public-123");
    await user.click(screen.getByRole("button", { name: "Connect" }));

    await waitFor(() => expect(exchangePlaidPublicToken).toHaveBeenCalledWith("biz-1", "public-123"));

    const syncButtons = screen.getAllByRole("button", { name: /sync now/i });
    await user.click(syncButtons[0]);
    await waitFor(() => expect(syncIntegration).toHaveBeenCalledWith("biz-1", "plaid"));

    await user.click(screen.getByRole("button", { name: /replay/i }));
    await waitFor(() => expect(replayIntegration).toHaveBeenCalledWith("biz-1", "plaid"));

    await user.click(screen.getByRole("button", { name: /disable/i }));
    await waitFor(() => expect(disableIntegration).toHaveBeenCalledWith("biz-1", "plaid"));
  });
});
