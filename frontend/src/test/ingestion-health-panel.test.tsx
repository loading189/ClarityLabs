import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SignalsTab from "../features/signals/SignalsTab";
import type { BusinessDetail } from "../types";
import * as categorizeApi from "../api/categorize";
import * as diagnosticsApi from "../api/diagnostics";
import * as integrationsApi from "../api/integrations";

vi.mock("../api/categorize", async () => {
  const actual = await vi.importActual<typeof import("../api/categorize")>("../api/categorize");
  return { ...actual, getCategorizeMetrics: vi.fn() };
});

vi.mock("../api/diagnostics", async () => {
  const actual = await vi.importActual<typeof import("../api/diagnostics")>("../api/diagnostics");
  return { ...actual, getDiagnosticsReconcile: vi.fn(), getIntegrationRuns: vi.fn() };
});

vi.mock("../api/integrations", async () => {
  const actual = await vi.importActual<typeof import("../api/integrations")>("../api/integrations");
  return { ...actual, syncIntegration: vi.fn() };
});

describe("SignalsTab ingestion health panel", () => {
  it("renders reconcile counts and triggers sync", async () => {
    const businessId = "11111111-1111-4111-8111-111111111111";
    const detail: BusinessDetail = {
      business_id: businessId,
      name: "Demo Co",
      as_of: "2024-02-01",
      risk: "green",
      health_score: 82,
      highlights: [],
      signals: [],
      health_signals: [],
      ledger_preview: [],
    };

    (categorizeApi.getCategorizeMetrics as any).mockResolvedValueOnce({
      total_events: 0,
      posted: 0,
      uncategorized: 0,
      suggestion_coverage: 0,
      brain_coverage: 0,
    });
    (diagnosticsApi.getDiagnosticsReconcile as any).mockResolvedValue({
      business_id: businessId,
      counts: { raw_events_total: 4, posted_txns_total: 3, categorized_txns_total: 2 },
      latest_markers: {},
      connections: [
        {
          provider: "plaid",
          status: "connected",
          is_enabled: true,
          provider_cursor: "cursor_1",
          last_ingested_source_event_id: "tx_1",
          last_processed_source_event_id: "tx_1",
          processing_stale: false,
        },
      ],
    });
    (diagnosticsApi.getIntegrationRuns as any).mockResolvedValue([]);
    (integrationsApi.syncIntegration as any).mockResolvedValueOnce({});

    render(<SignalsTab detail={detail} />);

    expect(await screen.findByText("Ingestion health")).toBeInTheDocument();
    expect(await screen.findByText("4")).toBeInTheDocument();
    expect(screen.getByText("Processing stale")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Run sync" }));

    await waitFor(() => {
      expect(integrationsApi.syncIntegration).toHaveBeenCalledWith(businessId, "plaid");
    });
  });
});
