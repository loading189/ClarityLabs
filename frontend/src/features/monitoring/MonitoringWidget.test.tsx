import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import MonitoringWidget from "./MonitoringWidget";

const getMonitorStatus = vi.fn().mockResolvedValue({
  business_id: "biz-1",
  last_pulse_at: new Date("2024-06-01T10:00:00Z").toISOString(),
  newest_event_at: new Date("2024-06-01T09:30:00Z").toISOString(),
  open_count: 2,
  counts: { by_status: { open: 2 }, by_severity: { red: 1, yellow: 1 } },
});

const runMonitorPulse = vi.fn().mockResolvedValue({
  ran: true,
  last_pulse_at: new Date("2024-06-01T10:05:00Z").toISOString(),
  newest_event_at: new Date("2024-06-01T09:30:00Z").toISOString(),
  counts: { by_status: { open: 2 }, by_severity: { red: 1, yellow: 1 } },
  touched_signal_ids: ["sig-1"],
});

const listSignalStates = vi.fn().mockResolvedValue({ signals: [], meta: {} });

vi.mock("../../api/monitor", () => ({
  getMonitorStatus: (...args: unknown[]) => getMonitorStatus(...args),
  runMonitorPulse: (...args: unknown[]) => runMonitorPulse(...args),
}));

vi.mock("../../api/signals", () => ({
  listSignalStates: (...args: unknown[]) => listSignalStates(...args),
}));

describe("MonitoringWidget", () => {
  it("runs a pulse and refreshes status", async () => {
    render(
      <MemoryRouter>
        <MonitoringWidget businessId="biz-1" />
      </MemoryRouter>
    );

    await waitFor(() => expect(getMonitorStatus).toHaveBeenCalledTimes(1));

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Run check now/i }));

    await waitFor(() => expect(runMonitorPulse).toHaveBeenCalledWith("biz-1"));
    await waitFor(() => expect(getMonitorStatus).toHaveBeenCalledTimes(2));
  });
});
