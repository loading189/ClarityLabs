import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import IntegrationsPage from "../app/routes/IntegrationsPage";
import * as integrationsApi from "../api/integrations";

vi.mock("../api/integrations", async () => {
  const actual = await vi.importActual<typeof import("../api/integrations")>("../api/integrations");
  return {
    ...actual,
    getIntegrationConnections: vi.fn(),
    syncIntegration: vi.fn(),
    toggleIntegration: vi.fn(),
    replayIntegration: vi.fn(),
    disconnectIntegration: vi.fn(),
  };
});

describe("IntegrationsPage", () => {
  it("renders connection status and triggers actions", async () => {
    const businessId = "11111111-1111-4111-8111-111111111111";
    const initial = [
      {
        id: "conn_1",
        business_id: businessId,
        provider: "plaid",
        is_enabled: true,
        status: "connected",
        provider_cursor: "cursor_123456789",
        last_ingested_source_event_id: "tx_1",
        last_processed_source_event_id: "tx_1",
      },
    ];
    const updated = [
      {
        ...initial[0],
        status: "error",
      },
    ];
    (integrationsApi.getIntegrationConnections as any)
      .mockResolvedValueOnce(initial)
      .mockResolvedValueOnce(updated);
    (integrationsApi.syncIntegration as any).mockResolvedValueOnce({});

    render(
      <MemoryRouter initialEntries={[`/app/${businessId}/integrations`]}>
        <Routes>
          <Route path="/app/:businessId/integrations" element={<IntegrationsPage />} />
        </Routes>
      </MemoryRouter>
    );

    expect(await screen.findByText("plaid")).toBeInTheDocument();
    expect(screen.getByText("connected")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Sync now" }));

    await waitFor(() => {
      expect(integrationsApi.syncIntegration).toHaveBeenCalledWith(businessId, "plaid");
    });

    expect(await screen.findByText("error")).toBeInTheDocument();
  });
});
