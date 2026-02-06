import { afterEach, describe, expect, it, vi } from "vitest";
import { apiGet, ApiError, API_BASE } from "./client";

describe("apiGet", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("handles non-JSON error responses without secondary parse failures", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("Internal Server Error", {
        status: 500,
        statusText: "Internal Server Error",
        headers: { "Content-Type": "text/plain" },
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiGet("/api/changes")).rejects.toBeInstanceOf(ApiError);
    await expect(apiGet("/api/changes")).rejects.toMatchObject({
      status: 500,
      url: `${API_BASE}/api/changes`,
    });
  });
});
