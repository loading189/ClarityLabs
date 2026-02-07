import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { AppStateProvider } from "../../app/state/appState";
import AssistantPage from "./AssistantPage";

const fetchAssistantSummary = vi.fn();
const postAssistantAction = vi.fn();
const fetchIngestionDiagnostics = vi.fn();
const fetchIngestionReconcile = vi.fn();
const getAuditLog = vi.fn();
const reprocessPipeline = vi.fn();
const syncPlaid = vi.fn();

vi.mock("../../api/assistantTools", () => ({
  fetchAssistantSummary: (...args: unknown[]) => fetchAssistantSummary(...args),
  postAssistantAction: (...args: unknown[]) => postAssistantAction(...args),
}));
vi.mock("../../api/ingestionDiagnostics", () => ({
  fetchIngestionDiagnostics: (...args: unknown[]) => fetchIngestionDiagnostics(...args),
}));
vi.mock("../../api/ingestionReconcile", () => ({
  fetchIngestionReconcile: (...args: unknown[]) => fetchIngestionReconcile(...args),
}));
vi.mock("../../api/audit", () => ({
  getAuditLog: (...args: unknown[]) => getAuditLog(...args),
}));
vi.mock("../../api/processing", () => ({
  reprocessPipeline: (...args: unknown[]) => reprocessPipeline(...args),
}));
vi.mock("../../api/plaid", () => ({
  syncPlaid: (...args: unknown[]) => syncPlaid(...args),
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
    fetchIngestionDiagnostics.mockResolvedValue({
      status_counts: { ingested: 0, normalized: 0, categorized: 0, posted: 0, ignored: 0, error: 0 },
      errors: [],
      connections: [],
      monitor_status: { stale: false, last_pulse_at: null, newest_event_at: null },
    });
    fetchIngestionReconcile.mockResolvedValue({
      counts: { raw_events: 0, posted_transactions: 0, categorized_transactions: 0 },
      latest_markers: { raw_event_occurred_at: null, raw_event_source_event_id: null, connections: [] },
    });
    getAuditLog.mockResolvedValue({ items: [] });
    postAssistantAction.mockResolvedValue({ ok: true, result: {} });
    reprocessPipeline.mockResolvedValue({ ok: true });
    syncPlaid.mockResolvedValue({ provider: "plaid", inserted: 0, skipped: 0 });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("does not auto-navigate on load", async () => {
    renderAssistant();
    await waitFor(() => expect(fetchAssistantSummary).toHaveBeenCalled());
    await waitFor(() => expect(fetchIngestionDiagnostics).toHaveBeenCalled());
    await waitFor(() => expect(fetchIngestionReconcile).toHaveBeenCalled());
    await waitFor(() => expect(getAuditLog).toHaveBeenCalled());
    expect(screen.getByTestId("location").textContent).toBe("/app/biz-1/assistant");
    expect(postAssistantAction).not.toHaveBeenCalled();
  });

  it("shows ingestion health panel and diagnostics drawer", async () => {
    const user = userEvent.setup();
    fetchIngestionDiagnostics.mockResolvedValueOnce({
      status_counts: { ingested: 0, normalized: 1, categorized: 0, posted: 0, ignored: 0, error: 2 },
      errors: [
        {
          source_event_id: "evt-bad",
          provider: "bank",
          error_code: "ValueError",
          error_detail: "bad payload",
          updated_at: "2025-01-01T00:00:00Z",
        },
      ],
      connections: [
        {
          provider: "stripe",
          status: "connected",
          last_sync_at: null,
          last_cursor: "cursor-1",
          last_cursor_at: "2025-01-02T00:00:00Z",
          last_webhook_at: "2025-01-03T00:00:00Z",
          last_ingest_counts: { inserted: 1, skipped: 0 },
          last_error: null,
        },
      ],
      monitor_status: { stale: false, last_pulse_at: null, newest_event_at: null, gating_reason: null },
    });
    fetchIngestionReconcile.mockResolvedValueOnce({
      counts: { raw_events: 3, posted_transactions: 2, categorized_transactions: 2 },
      latest_markers: {
        raw_event_occurred_at: "2025-01-02T00:00:00Z",
        raw_event_source_event_id: "evt-1",
        connections: [
          {
            provider: "stripe",
            status: "connected",
            provider_cursor: "cursor-1",
            provider_cursor_at: "2025-01-02T00:00:00Z",
            last_ingested_at: "2025-01-02T00:00:00Z",
            last_ingested_source_event_id: "evt-1",
            last_processed_at: "2025-01-02T00:00:00Z",
            last_processed_source_event_id: "evt-1",
            mismatch_flags: { processing_stale: false, cursor_missing_timestamp: false },
          },
        ],
      },
    });
    getAuditLog.mockResolvedValueOnce({
      items: [
        {
          id: "audit-1",
          business_id: "biz-1",
          event_type: "processing_completed",
          actor: "system",
          reason: null,
          source_event_id: null,
          rule_id: null,
          before_state: null,
          after_state: null,
          created_at: "2025-01-02T00:00:00Z",
        },
      ],
    });

    renderAssistant();

    expect(await screen.findByText("Ingestion Health")).toBeInTheDocument();
    expect(await screen.findByText("3")).toBeInTheDocument();
    expect(await screen.findByText("processing_completed")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /view ingestion diagnostics/i }));
    expect(await screen.findAllByText("Processing errors")).toHaveLength(2);
    expect(await screen.findByText("evt-bad")).toBeInTheDocument();
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

  it("runs ingestion sync and reprocess from health panel", async () => {
    const user = userEvent.setup();
    renderAssistant();

    const syncButton = await screen.findByRole("button", { name: /run sync/i });
    await user.click(syncButton);
    await waitFor(() => expect(postAssistantAction).toHaveBeenCalledWith("biz-1", "sync_integrations"));

    const reprocessButton = await screen.findByRole("button", { name: /reprocess/i });
    await user.click(reprocessButton);
    await waitFor(() => expect(reprocessPipeline).toHaveBeenCalledWith("biz-1", { mode: "from_last_cursor" }));
  });

  it("syncs Plaid from the getting started checklist", async () => {
    const user = userEvent.setup();
    fetchAssistantSummary.mockResolvedValue({
      business_id: "biz-1",
      integrations: [{ provider: "plaid", status: "connected" }],
      monitor_status: { stale: false, gated: false },
      open_signals: 0,
      uncategorized_count: 0,
      audit_events: [],
      top_vendors: [],
    });

    renderAssistant();
    const button = await screen.findByRole("button", { name: /sync now/i });
    await user.click(button);

    await waitFor(() => expect(syncPlaid).toHaveBeenCalledWith("biz-1"));
  });
});
