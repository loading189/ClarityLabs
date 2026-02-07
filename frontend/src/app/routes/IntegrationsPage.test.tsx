import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import IntegrationsPage from "./IntegrationsPage";

const listIntegrationConnections = vi.fn();
const createPlaidLinkToken = vi.fn();
const exchangePlaidPublicToken = vi.fn();
const syncPlaid = vi.fn();

vi.mock("../../api/integrationConnections", () => ({
  listIntegrationConnections: (...args: unknown[]) => listIntegrationConnections(...args),
}));
vi.mock("../../api/plaid", () => ({
  createPlaidLinkToken: (...args: unknown[]) => createPlaidLinkToken(...args),
  exchangePlaidPublicToken: (...args: unknown[]) => exchangePlaidPublicToken(...args),
  syncPlaid: (...args: unknown[]) => syncPlaid(...args),
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
        last_sync_at: "2025-01-01T00:00:00Z",
        last_cursor: "cursor-2",
        last_error: null,
      },
    ]);
    createPlaidLinkToken.mockResolvedValue({ link_token: "link-1" });
    exchangePlaidPublicToken.mockResolvedValue({ connection: { provider: "plaid" } });
    syncPlaid.mockResolvedValue({ provider: "plaid", inserted: 1, skipped: 0 });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders connection status and triggers connect + sync", async () => {
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByText(/connection health/i)).toBeInTheDocument();
    expect(await screen.findByText(/connected/i)).toBeInTheDocument();

    const input = screen.getByPlaceholderText(/paste plaid public_token/i);
    await user.type(input, "public-123");
    await user.click(screen.getByRole("button", { name: /connect/i }));

    await waitFor(() => expect(exchangePlaidPublicToken).toHaveBeenCalledWith("biz-1", "public-123"));

    await user.click(screen.getByRole("button", { name: /sync now/i }));
    await waitFor(() => expect(syncPlaid).toHaveBeenCalledWith("biz-1"));
  });
});
