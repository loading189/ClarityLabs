import { describe, expect, it, vi, beforeEach } from "vitest";

const apiGet = vi.fn();

vi.mock("./client", () => ({
  apiDelete: vi.fn(),
  apiGet: (...args: unknown[]) => apiGet(...args),
  apiPatch: vi.fn(),
  apiPost: vi.fn(),
}));

import { fetchTxnsToCategorize } from "./categorize";

describe("fetchTxnsToCategorize", () => {
  beforeEach(() => {
    apiGet.mockReset();
  });

  it("returns paged payload as-is when backend already returns paging", async () => {
    apiGet.mockResolvedValue({
      items: [{ source_event_id: "evt-1" }],
      total_count: 10,
      has_more: true,
      next_offset: 50,
    });

    const result = await fetchTxnsToCategorize("biz-1", { limit: 50, offset: 0 });

    expect(result).toEqual({
      items: [{ source_event_id: "evt-1" }],
      total_count: 10,
      has_more: true,
      next_offset: 50,
    });
  });

  it("wraps legacy array payloads into paged structure", async () => {
    apiGet.mockResolvedValue([{ source_event_id: "evt-1" }, { source_event_id: "evt-2" }]);

    const result = await fetchTxnsToCategorize("biz-1", { limit: 50, offset: 0 });

    expect(result).toEqual({
      items: [{ source_event_id: "evt-1" }, { source_event_id: "evt-2" }],
      total_count: 2,
      has_more: false,
      next_offset: null,
    });
  });
});
